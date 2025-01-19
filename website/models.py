import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from urllib.parse import urlparse

import requests
from annoying.fields import AutoOneToOneField
from captcha.fields import CaptchaField
from colorthief import ColorThief
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.validators import MaxValueValidator, MinValueValidator, URLValidator
from django.db import models, transaction
from django.db.models import Count
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils import timezone
from google.api_core.exceptions import NotFound
from google.cloud import storage
from mdeditor.fields import MDTextField
from rest_framework.authtoken.models import Token

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)
        Wallet.objects.create(user=instance)


class Subscription(models.Model):
    name = models.CharField(max_length=25, null=False, blank=True)
    charge_per_month = models.IntegerField(null=False, blank=True)
    hunt_per_domain = models.IntegerField(null=False, blank=True)
    number_of_domains = models.IntegerField(null=False, blank=True)
    feature = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)


class Tag(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super(Tag, self).save(*args, **kwargs)

    def __str__(self):
        return self.name


class IntegrationServices(Enum):
    SLACK = "slack"


class Integration(models.Model):
    service_name = models.CharField(
        max_length=20,
        choices=[(tag.value, tag.name) for tag in IntegrationServices],
        null=True,
        blank=True,
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="organization_integrations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.organization.name} - {self.service_name} Integration"


class SlackIntegration(models.Model):
    integration = models.OneToOneField(
        Integration, on_delete=models.CASCADE, related_name="slack_integration"
    )
    bot_access_token = models.CharField(
        max_length=255, null=True, blank=True
    )  # will be different for each workspace
    workspace_name = models.CharField(max_length=255, null=True, blank=True)
    default_channel_name = models.CharField(
        max_length=255, null=True, blank=True
    )  # Default channel ID
    default_channel_id = models.CharField(max_length=255, null=True, blank=True)
    daily_updates = models.BooleanField(default=False)
    daily_update_time = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(23)],  # Valid hours: 0–23
        help_text="The hour of the day (0-23) to send daily updates",
    )

    def __str__(self):
        return f"Slack Integration for {self.integration.organization.name}"


class OrganisationType(Enum):
    ORGANIZATION = "organization"
    INDIVIDUAL = "individual"
    TEAM = "team"


class Organization(models.Model):
    admin = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    managers = models.ManyToManyField(User, related_name="user_organizations")
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, null=True, blank=True)
    logo = models.ImageField(upload_to="organization_logos", null=True, blank=True)
    url = models.URLField(unique=True)
    email = models.EmailField(null=True, blank=True)
    twitter = models.CharField(max_length=30, null=True, blank=True)
    facebook = models.URLField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    subscription = models.ForeignKey(Subscription, null=True, blank=True, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=False)
    tags = models.ManyToManyField(Tag, blank=True)
    integrations = models.ManyToManyField(Integration, related_name="organizations")
    trademark_count = models.IntegerField(default=0)
    trademark_check_date = models.DateTimeField(null=True, blank=True)
    team_points = models.IntegerField(default=0)
    type = models.CharField(
        max_length=15,
        choices=[(tag.value, tag.name) for tag in OrganisationType],
        default=OrganisationType.ORGANIZATION.value,
    )

    def __str__(self):
        return self.name


class JoinRequest(models.Model):
    team = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_accepted = models.BooleanField(default=False)


class Domain(models.Model):
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE)
    managers = models.ManyToManyField(User, related_name="user_domains", blank=True)
    name = models.CharField(max_length=255, unique=True)
    url = models.URLField()
    logo = models.ImageField(upload_to="logos", null=True, blank=True)
    webshot = models.ImageField(upload_to="webshots", null=True, blank=True)
    clicks = models.IntegerField(null=True, blank=True)
    email_event = models.CharField(max_length=255, default="", null=True, blank=True)
    color = models.CharField(max_length=10, null=True, blank=True)
    github = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    twitter = models.CharField(max_length=30, null=True, blank=True)
    facebook = models.URLField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    tags = models.ManyToManyField(Tag, blank=True)

    def __unicode__(self):
        return self.name

    def __str__(self):
        return self.name

    @property
    def open_issues(self):
        return Issue.objects.filter(domain=self).exclude(status="closed")

    @property
    def closed_issues(self):
        return Issue.objects.filter(domain=self).filter(status="closed")

    @property
    def top_tester(self):
        return (
            User.objects.filter(issue__domain=self)
            .annotate(total=Count("issue"))
            .order_by("-total")
            .first()
        )

    @property
    def get_name(self):
        parsed_url = urlparse(self.url)
        return parsed_url.netloc.split(".")[-2:][0].title()

    def get_logo(self):
        if self.logo:
            return self.logo.url
        image_request = requests.get("https://logo.clearbit.com/" + self.name)
        try:
            if image_request.status_code == 200:
                image_content = ContentFile(image_request.content)
                self.logo.save(self.name + ".jpg", image_content)
                return self.logo.url

        except:
            favicon_url = self.url + "/favicon.ico"
            return favicon_url

    @property
    def get_color(self):
        if self.color:
            return self.color
        else:
            if not self.logo:
                self.get_logo()
            try:
                color_thief = ColorThief(self.logo)
                self.color = "#%02x%02x%02x" % color_thief.get_color(quality=1)
            except:
                self.color = "#0000ff"
            self.save()
            return self.color

    @property
    def hostname_domain(self):
        parsed_url = urlparse(self.url)
        return parsed_url.hostname

    @property
    def domain_name(self):
        parsed_url = urlparse(self.url)
        domain = parsed_url.path
        if domain is not None:
            temp = domain.rsplit(".")
            if len(temp) == 3:
                domain = temp[1] + "." + temp[2]
        return domain

    def get_absolute_url(self):
        return "/domain/" + self.name

    def get_or_set_x_url(self, name):
        if self.twitter:
            return self.twitter

        validate = URLValidator(schemes=["https"])  # Only allow HTTPS URLs
        try:
            twitter_url = "https://twitter.com/%s" % (name)
            validate(twitter_url)
            self.twitter = name
            self.save()
            return name
        except ValidationError:
            pass


def validate_image(fieldfile_obj):
    try:
        filesize = fieldfile_obj.file.size
    except:
        filesize = fieldfile_obj.size
    megabyte_limit = 3.0
    if filesize > megabyte_limit * 1024 * 1024:
        raise ValidationError("Max file size is %sMB" % str(megabyte_limit))


class Hunt(models.Model):
    class Meta:
        ordering = ["-id"]

    domain = models.ForeignKey(Domain, on_delete=models.CASCADE)
    name = models.CharField(max_length=25)
    description = MDTextField(null=True, blank=True)
    url = models.URLField()
    prize = models.IntegerField(null=True, blank=True)
    prize_winner = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    prize_runner = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    prize_second_runner = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    logo = models.ImageField(upload_to="logos", null=True, blank=True)
    banner = models.ImageField(upload_to="banners", null=True, blank=True)
    plan = models.CharField(max_length=10)
    txn_id = models.CharField(max_length=50, null=True, blank=True)
    color = models.CharField(max_length=10, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    starts_on = models.DateTimeField(null=True, blank=True)
    end_on = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    result_published = models.BooleanField(default=False)
    modified = models.DateTimeField(auto_now=True)

    @property
    def domain_title(self):
        parsed_url = urlparse(self.url)
        return parsed_url.netloc.split(".")[-2:][0].title()

    def __str__(self) -> str:
        return self.name


class HuntPrize(models.Model):
    hunt = models.ForeignKey(Hunt, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    value = models.PositiveIntegerField(default=0)
    no_of_eligible_projects = models.PositiveIntegerField(default=1)  # no of winner in this prize
    valid_submissions_eligible = models.BooleanField(
        default=False
    )  # all valid submissions are winners in this prize
    prize_in_crypto = models.BooleanField(default=False)
    description = models.TextField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.hunt.name + self.name


class Issue(models.Model):
    labels = (
        (0, "General"),
        (1, "Number Error"),
        (2, "Functional"),
        (3, "Performance"),
        (4, "Security"),
        (5, "Typo"),
        (6, "Design"),
        (7, "Server Down"),
    )
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    team_members = models.ManyToManyField(User, related_name="reportmembers", blank=True)
    hunt = models.ForeignKey(Hunt, null=True, blank=True, on_delete=models.CASCADE)
    domain = models.ForeignKey(Domain, null=True, blank=True, on_delete=models.CASCADE)
    url = models.URLField()
    description = models.TextField()
    markdown_description = models.TextField(null=True, blank=True)
    captcha = CaptchaField()
    label = models.PositiveSmallIntegerField(choices=labels, default=0)
    views = models.IntegerField(null=True, blank=True)
    verified = models.BooleanField(default=False)
    score = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, default="open", null=True, blank=True)
    user_agent = models.CharField(max_length=255, default="", null=True, blank=True)
    ocr = models.TextField(default="", null=True, blank=True)
    screenshot = models.ImageField(
        upload_to="screenshots", null=True, blank=True, validators=[validate_image]
    )
    closed_by = models.ForeignKey(
        User, null=True, blank=True, related_name="closed_by", on_delete=models.CASCADE
    )
    closed_date = models.DateTimeField(default=None, null=True, blank=True)
    github_url = models.URLField(default="", null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    is_hidden = models.BooleanField(default=False)
    rewarded = models.PositiveIntegerField(default=0)  # money rewarded by the organization
    reporter_ip_address = models.GenericIPAddressField(null=True, blank=True)
    cve_id = models.CharField(max_length=16, null=True, blank=True)
    cve_score = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    comments = GenericRelation("comments.Comment")

    def __unicode__(self):
        return self.description

    def __str__(self):
        return self.description

    @property
    def domain_title(self):
        parsed_url = urlparse(self.url)
        return parsed_url.netloc.split(".")[-2:][0].title()

    @property
    def hostname_domain(self):
        parsed_url = urlparse(self.url)
        return parsed_url.hostname

    @property
    def domain_name(self):
        parsed_url = urlparse(self.url)
        domain = parsed_url.hostname
        return domain

    def get_twitter_message(self):
        issue_link = " " + settings.DOMAIN_NAME + "/issue/" + str(self.id)
        prefix = "Bug found on @"
        spacer = " | "
        msg = (
            prefix
            + self.domain_title
            + spacer
            + self.description[
                : 140 - (len(prefix) + len(self.domain_title) + len(spacer) + len(issue_link))
            ]
            + issue_link
        )
        return msg

    def remove_user(self):
        self.user = None
        self.save()

    def get_absolute_url(self):
        return "/issue/" + str(self.id)

    def get_cve_score(self):
        if self.cve_id is None:
            return None
        try:
            url = "https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=%s" % (self.cve_id)
            response = requests.get(url).json()
            results = response["resultsPerPage"]
            if results != 0:
                metrics = response["vulnerabilities"][0]["cve"]["metrics"]
                if metrics:
                    cvss_metric_v = next(iter(metrics))
                    return metrics[cvss_metric_v][0]["cvssData"]["baseScore"]
        except (requests.exceptions.HTTPError, requests.exceptions.ReadTimeout) as e:
            print(e)
            return None

    class Meta:
        ordering = ["-created"]


def is_using_gcs():
    """
    Determine if Google Cloud Storage is being used as the backend.
    """
    if hasattr(settings, "STORAGES"):
        backend = settings.STORAGES.get("default", {}).get("BACKEND", "")
    else:
        backend = getattr(settings, "DEFAULT_FILE_STORAGE", "")

    return backend == "storages.backends.gcloud.GoogleCloudStorage"


if is_using_gcs():

    @receiver(post_delete, sender=Issue)
    def delete_image_on_issue_delete(sender, instance, **kwargs):
        if instance.screenshot:
            client = storage.Client()
            bucket = client.bucket(settings.GS_BUCKET_NAME)
            blob_name = instance.screenshot.name
            blob = bucket.blob(blob_name)
            try:
                logger.info(f"Attempting to delete image from Google Cloud Storage: {blob_name}")
                blob.delete()
                logger.info(f"Successfully deleted image from Google Cloud Storage: {blob_name}")
            except NotFound:
                logger.warning(f"File not found in Google Cloud Storage: {blob_name}")
            except Exception as e:
                logger.error(
                    f"Error deleting image from Google Cloud Storage: {blob_name} - {str(e)}"
                )

else:

    @receiver(post_delete, sender=Issue)
    def delete_image_on_issue_delete(sender, instance, **kwargs):
        if instance.screenshot:
            instance.screenshot.delete(save=False)


class IssueScreenshot(models.Model):
    image = models.ImageField(upload_to="screenshots", validators=[validate_image])
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="screenshots")
    created = models.DateTimeField(auto_now_add=True)


if is_using_gcs():

    @receiver(post_delete, sender=IssueScreenshot)
    def delete_image_on_post_delete(sender, instance, **kwargs):
        if instance.image:
            client = storage.Client()
            bucket = client.bucket(settings.GS_BUCKET_NAME)
            blob_name = instance.image.name
            blob = bucket.blob(blob_name)
            try:
                logger.info(f"Attempting to delete image from Google Cloud Storage: {blob_name}")
                blob.delete()
                logger.info(f"Successfully deleted image from Google Cloud Storage: {blob_name}")
            except NotFound:
                logger.warning(f"File not found in Google Cloud Storage: {blob_name}")
            except Exception as e:
                logger.error(
                    f"Error deleting image from Google Cloud Storage: {blob_name} - {str(e)}"
                )

else:

    @receiver(post_delete, sender=IssueScreenshot)
    def delete_image_on_post_delete(sender, instance, **kwargs):
        if instance.image:
            instance.image.delete(save=False)


@receiver(post_save, sender=Issue)
def update_issue_image_access(sender, instance, **kwargs):
    if instance.is_hidden:
        issue_screenshot_list = IssueScreenshot.objects.filter(issue=instance.id)
        for screenshot in issue_screenshot_list:
            old_name = screenshot.image.name
            if "hidden" not in old_name:
                filename = screenshot.image.name
                extension = filename.split(".")[-1]
                name = filename[:20] + "hidden" + str(uuid.uuid4())[:40] + "." + extension
                default_storage.save(f"screenshots/{name}", screenshot.image)
                default_storage.delete(old_name)
                screenshot.image = f"screenshots/{name}"
                screenshot.image.name = f"screenshots/{name}"
                screenshot.save()


TWITTER_MAXLENGTH = getattr(settings, "TWITTER_MAXLENGTH", 140)


class Winner(models.Model):
    hunt = models.ForeignKey(Hunt, null=True, blank=True, on_delete=models.CASCADE)
    winner = models.ForeignKey(
        User, related_name="winner", null=True, blank=True, on_delete=models.CASCADE
    )
    runner = models.ForeignKey(
        User, related_name="runner", null=True, blank=True, on_delete=models.CASCADE
    )
    second_runner = models.ForeignKey(
        User,
        related_name="second_runner",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    prize_distributed = models.BooleanField(default=False)
    prize = models.ForeignKey(HuntPrize, null=True, blank=True, on_delete=models.CASCADE)
    prize_amount = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    created = models.DateTimeField(auto_now_add=True)


class Points(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    issue = models.ForeignKey(Issue, null=True, blank=True, on_delete=models.CASCADE)
    domain = models.ForeignKey(Domain, null=True, blank=True, on_delete=models.CASCADE)
    score = models.IntegerField()
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    reason = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.score} points"


class InviteFriend(models.Model):
    sender = models.ForeignKey(User, related_name="sent_invites", on_delete=models.CASCADE)
    recipients = models.ManyToManyField(User, related_name="received_invites", blank=True)
    referral_code = models.CharField(max_length=100, default=uuid.uuid4, editable=False)
    point_by_referral = models.IntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invite from {self.sender}"


def user_images_path(instance, filename):
    from django.template.defaultfilters import slugify

    filename, ext = os.path.splitext(filename)
    return "avatars/user_{0}/{1}{2}".format(instance.user.id, slugify(filename), ext)


class UserProfile(models.Model):
    title = (
        (0, "Unrated"),
        (1, "Bronze"),
        (2, "Silver"),
        (3, "Gold"),
        (4, "Platinum"),
    )
    follows = models.ManyToManyField("self", related_name="follower", symmetrical=False, blank=True)
    user = AutoOneToOneField("auth.user", related_name="userprofile", on_delete=models.CASCADE)
    user_avatar = models.ImageField(upload_to=user_images_path, blank=True, null=True)
    title = models.IntegerField(choices=title, default=0)
    role = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    winnings = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    issue_upvoted = models.ManyToManyField(Issue, blank=True, related_name="upvoted")
    issue_downvoted = models.ManyToManyField(Issue, blank=True, related_name="downvoted")
    issue_saved = models.ManyToManyField(Issue, blank=True, related_name="saved")
    issue_flaged = models.ManyToManyField(Issue, blank=True, related_name="flaged")
    issues_hidden = models.BooleanField(default=False)

    subscribed_domains = models.ManyToManyField(
        Domain, related_name="user_subscribed_domains", blank=True
    )
    subscribed_users = models.ManyToManyField(
        User, related_name="user_subscribed_users", blank=True
    )
    btc_address = models.CharField(max_length=100, blank=True, null=True)
    bch_address = models.CharField(max_length=100, blank=True, null=True)
    eth_address = models.CharField(max_length=100, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True)
    x_username = models.CharField(max_length=50, blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    github_url = models.URLField(blank=True, null=True)
    website_url = models.URLField(blank=True, null=True)
    discounted_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    modified = models.DateTimeField(auto_now=True)
    visit_count = models.PositiveIntegerField(default=0)
    team = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="user_profiles",
        null=True,
        blank=True,
    )

    def check_team_membership(self):
        return self.team is not None

    current_streak = models.IntegerField(default=0)
    longest_streak = models.IntegerField(default=0)
    last_check_in = models.DateField(null=True, blank=True)

    def avatar(self, size=36):
        if self.user_avatar:
            return self.user_avatar.url

        for account in self.user.socialaccount_set.all():
            if "avatar_url" in account.extra_data:
                return account.extra_data["avatar_url"]
            elif "picture" in account.extra_data:
                return account.extra_data["picture"]

    def __unicode__(self):
        return self.user.email

    def update_streak_and_award_points(self, check_in_date=None):
        """
        Update streak based on consecutive daily check-ins and award points
        """
        # Use current date if no check-in date provided
        if check_in_date is None:
            check_in_date = timezone.now().date()

        try:
            with transaction.atomic():
                # Streak logic
                if not self.last_check_in or check_in_date == self.last_check_in + timedelta(
                    days=1
                ):
                    self.current_streak += 1
                    self.longest_streak = max(self.current_streak, self.longest_streak)
                # If check-in is not consecutive, reset streak
                elif check_in_date > self.last_check_in + timedelta(days=1):
                    self.current_streak = 1

                Points.objects.get_or_create(
                    user=self.user,
                    reason="Daily check-in",
                    created__date=datetime.today().date(),
                    defaults={"score": 5},
                )

                points_awarded = 0
                if self.current_streak == 7:
                    points_awarded += 20
                    reason = "7-day streak milestone achieved!"
                elif self.current_streak == 15:
                    points_awarded += 30
                    reason = "15-day streak milestone achieved!"
                elif self.current_streak == 30:
                    points_awarded += 50
                    reason = "30-day streak milestone achieved!"
                elif self.current_streak == 100:
                    points_awarded += 150
                    reason = "100-day streak milestone achieved!"
                elif self.current_streak == 180:
                    points_awarded += 300
                    reason = "180-day streak milestone achieved!"
                elif self.current_streak == 365:
                    points_awarded += 500
                    reason = "365-day streak milestone achieved!"

                if points_awarded != 0:
                    Points.objects.create(user=self.user, score=points_awarded, reason=reason)

                # Update last check-in and save
                self.last_check_in = check_in_date
                self.save()

                self.award_streak_badges()

        except Exception as e:
            # Log the error or handle it appropriately
            logger.error(f"Error in check-in process: {e}")
            return False

        return True

    def award_streak_badges(self):
        """
        Award badges for streak milestones
        """
        streak_badges = {
            7: "Weekly Streak",
            15: "Half-Month Streak",
            30: "Monthly Streak",
            100: "100 Day Streak",
            180: "Six Month Streak",
            365: "Yearly Streak",
        }

        for milestone, badge_title in streak_badges.items():
            if self.current_streak >= milestone:
                badge, _ = Badge.objects.get(
                    title=badge_title,
                )

                # Avoid duplicate badge awards
                if not UserBadge.objects.filter(user=self.user, badge=badge).exists():
                    UserBadge.objects.create(user=self.user, badge=badge)


def create_profile(sender, **kwargs):
    user = kwargs["instance"]
    if kwargs["created"]:
        profile = UserProfile(user=user)
        profile.save()


post_save.connect(create_profile, sender=User)


class IP(models.Model):
    address = models.CharField(max_length=39, null=True, blank=True)
    user = models.CharField(max_length=150, null=True, blank=True)
    issuenumber = models.IntegerField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    agent = models.TextField(null=True, blank=True)
    count = models.BigIntegerField(default=1)
    path = models.CharField(max_length=255, null=True, blank=True)
    method = models.CharField(max_length=10, null=True, blank=True)
    referer = models.CharField(max_length=255, null=True, blank=True)


class OrganizationAdmin(models.Model):
    role = (
        (0, "Admin"),
        (1, "Moderator"),
    )
    role = models.IntegerField(choices=role, default=0)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, null=True, blank=True, on_delete=models.CASCADE)
    domain = models.ForeignKey(Domain, null=True, blank=True, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)


class Wallet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    account_id = models.TextField(null=True, blank=True)
    current_balance = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    created = models.DateTimeField(auto_now_add=True)

    def deposit(self, value):
        self.transaction_set.create(
            value=value, running_balance=self.current_balance + Decimal(value)
        )
        self.current_balance += Decimal(value)
        self.save()

    def withdraw(self, value):
        if value > self.current_balance:
            raise Exception("This wallet has insufficient balance.")

        self.transaction_set.create(
            value=-value, running_balance=self.current_balance - Decimal(value)
        )
        self.current_balance -= Decimal(value)
        self.save()

    def transfer(self, wallet, value):
        self.withdraw(value)
        wallet.deposit(value)


class Transaction(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    value = models.DecimalField(max_digits=6, decimal_places=2)
    running_balance = models.DecimalField(max_digits=6, decimal_places=2)
    created = models.DateTimeField(auto_now_add=True)


class Payment(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE)
    value = models.DecimalField(max_digits=6, decimal_places=2)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)


class Monitor(models.Model):
    url = models.URLField()
    keyword = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    last_checked_time = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("UP", "Up"),
            ("DOWN", "Down"),
        ],
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return f"Monitor for {self.url} by {self.user}"


class Bid(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # link this to our issue model
    issue_url = models.URLField()
    created = models.DateTimeField(default=timezone.now)
    modified = models.DateTimeField(default=timezone.now)
    amount_bch = models.DecimalField(max_digits=16, decimal_places=8, default=0)
    status = models.CharField(default="Open", max_length=10)
    pr_link = models.URLField(blank=True, null=True)
    bch_address = models.CharField(blank=True, null=True, max_length=45)

    # def save(self, *args, **kwargs):
    #     if (
    #         self.status == "Open"
    #         and (timezone.now() - self.created).total_seconds() >= 24 * 60 * 60
    #     ):
    #         self.status = "Selected"
    #         self.modified = timezone.now()
    #         email_body = f"This bid was selected:\nIssue URL: {self.issue_url}\nUser: {self.user}\nCurrent Bid: {self.current_bid}\nCreated on: {self.created}\nBid Amount: {self.amount}"
    #         send_mail(
    #             "Bid Closed",
    #             email_body,
    #             settings.EMAIL_HOST_USER,
    #             [settings.EMAIL_HOST_USER],
    #             fail_silently=False,
    #         )

    #     super().save(*args, **kwargs)


class ChatBotLog(models.Model):
    question = models.TextField()
    answer = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Q: {self.question} | A: {self.answer} at {self.created}"


class Suggestion(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField(max_length=1000, null=True, blank=True)
    up_votes = models.IntegerField(null=True, blank=True, default=0)
    down_votes = models.IntegerField(null=True, blank=True, default=0)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} by {self.user}"


class SuggestionVotes(models.Model):
    suggestion = models.ForeignKey(Suggestion, on_delete=models.CASCADE)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    up_vote = models.BooleanField(default=False)
    down_vote = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Suggestion {self.user}"


class Contributor(models.Model):
    name = models.CharField(max_length=255)
    github_id = models.IntegerField(unique=True)
    github_url = models.URLField()
    avatar_url = models.URLField()
    contributor_type = models.CharField(max_length=255)  # type = User, Bot ,... etc
    contributions = models.PositiveIntegerField()
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Project(models.Model):
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        related_name="projects",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    url = models.URLField(
        unique=True, null=True, blank=True
    )  # Made url nullable in case of no website
    project_visit_count = models.IntegerField(default=0)
    twitter = models.CharField(max_length=30, null=True, blank=True)
    facebook = models.URLField(null=True, blank=True)
    logo = models.ImageField(upload_to="project_logos", null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)  # Standardized field name
    modified = models.DateTimeField(auto_now=True)  # Standardized field name
    # add languages
    # add tags

    def save(self, *args, **kwargs):
        if not self.slug:
            slug = slugify(self.name)
            # Replace dots with dashes and limit length
            slug = slug.replace(".", "-")
            if len(slug) > 50:
                slug = slug[:50]
            # Ensure we have a valid slug
            if not slug:
                slug = f"project-{int(time.time())}"
            self.slug = slug
        super(Project, self).save(*args, **kwargs)

    def __str__(self):
        return self.name


class Contribution(models.Model):
    CONTRIBUTION_TYPES = [
        ("commit", "Commit"),
        ("issue_opened", "Issue Opened"),
        ("issue_closed", "Issue Closed"),
        ("issue_assigned", "Issue Assigned"),
        ("pull_request", "Pull Request"),
        ("comment", "Comment"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    repository = models.ForeignKey(Project, on_delete=models.CASCADE, null=True)
    contribution_type = models.CharField(
        max_length=20, choices=CONTRIBUTION_TYPES, default="commit"
    )
    github_username = models.CharField(max_length=255, default="")
    github_id = models.CharField(max_length=100, null=True, blank=True)
    github_url = models.URLField(null=True, blank=True)
    created = models.DateTimeField()
    status = models.CharField(max_length=50, choices=[("open", "Open"), ("closed", "Closed")])
    txid = models.CharField(max_length=64, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["github_id"]),
            models.Index(fields=["user", "created"]),
            models.Index(fields=["repository", "created"]),
        ]


class BaconToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created = models.DateTimeField(auto_now_add=True)
    contribution = models.OneToOneField(Contribution, on_delete=models.CASCADE)
    token_id = models.CharField(
        max_length=64, blank=True, null=True
    )  # Token ID from the Runes protocol

    def __str__(self):
        return f"{self.user.username} - {self.amount} BACON"


class Blocked(models.Model):
    address = models.GenericIPAddressField(null=True, blank=True)
    reason_for_block = models.TextField(blank=True, null=True, max_length=255)
    ip_network = models.GenericIPAddressField(null=True, blank=True)
    user_agent_string = models.CharField(max_length=255, default="", null=True, blank=True)
    count = models.IntegerField(default=1)
    created = models.DateField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"user agent : {self.user_agent_string} | IP : {self.address}"


@receiver(post_save, sender=Blocked)
@receiver(post_delete, sender=Blocked)
def clear_blocked_cache(sender, instance=None, **kwargs):
    """
    Clears the cache when a Blocked instance is created, updated, or deleted.
    """
    # Clear the cache
    cache.delete("blocked_ips")
    cache.delete("blocked_ip_network")
    cache.delete("blocked_agents")

    # Retrieve valid blocked IPs, IP networks, and user agents
    blocked_ips = Blocked.objects.values_list("address", flat=True)
    blocked_ip_network = Blocked.objects.values_list("ip_network", flat=True)
    blocked_agents = Blocked.objects.values_list("user_agent_string", flat=True)

    # Filter out None or invalid values
    blocked_ips = [ip for ip in blocked_ips if ip is not None]
    blocked_ip_network = [network for network in blocked_ip_network if network is not None]
    blocked_agents = [agent for agent in blocked_agents if agent is not None]

    # Set the cache with valid values
    cache.set("blocked_ips", blocked_ips, timeout=86400)
    cache.set("blocked_ip_network", blocked_ip_network, timeout=86400)
    cache.set("blocked_agents", blocked_agents, timeout=86400)


class TimeLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="timelogs"
    )
    # associate organization with sizzle
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="time_logs",
        null=True,
        blank=True,
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    github_issue_url = models.URLField(null=True, blank=True)  # URL field for GitHub issue
    created = models.DateTimeField(default=timezone.now, editable=False)

    def save(self, *args, **kwargs):
        if self.end_time and self.start_time <= self.end_time:
            self.duration = self.end_time - self.start_time
        super().save(*args, **kwargs)

    def __str__(self):
        return f"TimeLog by {self.user.username} from {self.start_time} to {self.end_time}"


class ActivityLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity_logs"
    )
    window_title = models.CharField(max_length=255)
    url = models.URLField(null=True, blank=True)  # URL field for activity-related URL
    recorded_at = models.DateTimeField(auto_now_add=True)
    created = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self):
        return f"ActivityLog by {self.user.username} at {self.recorded_at}"


class DailyStatusReport(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    previous_work = models.TextField()
    next_plan = models.TextField()
    blockers = models.TextField()
    goal_accomplished = models.BooleanField(default=False)
    current_mood = models.CharField(max_length=50, default="Happy 😊")
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Daily Status Report by {self.user.username} on {self.date}"


class IpReport(models.Model):
    IP_TYPE_CHOICES = [
        ("ipv4", "IPv4"),
        ("ipv6", "IPv6"),
    ]
    ACTIVITY_TYPE_CHOICES = [
        ("malicious", "Malicious"),
        ("friendly", "Friendly"),
    ]

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    activity_title = models.CharField(max_length=255)
    activity_type = models.CharField(max_length=50, choices=ACTIVITY_TYPE_CHOICES)
    ip_address = models.GenericIPAddressField()
    ip_type = models.CharField(max_length=10, choices=IP_TYPE_CHOICES)
    description = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    reporter_ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.ip_address} ({self.ip_type}) - {self.activity_title}"


class Activity(models.Model):
    ACTION_TYPES = [
        ("create", "Created"),
        ("update", "Updated"),
        ("delete", "Deleted"),
        ("signup", "Signed Up"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=10, choices=ACTION_TYPES)
    title = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    image = models.ImageField(null=True, blank=True, upload_to="activity_images/")
    url = models.URLField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Approval and Posting
    like_count = models.PositiveIntegerField(default=0)
    dislike_count = models.PositiveIntegerField(default=0)
    is_approved = models.BooleanField(default=False)  # Whether activity is approved
    is_posted_to_bluesky = models.BooleanField(default=False)  # Whether posted to BlueSky

    # Generic foreign key fields
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    related_object = GenericForeignKey("content_type", "object_id")

    # New fields for likes and dislikes
    likes = models.ManyToManyField(User, related_name="liked_activities", blank=True)
    dislikes = models.ManyToManyField(User, related_name="disliked_activities", blank=True)

    def __str__(self):
        return f"{self.title} by {self.user.username} at {self.timestamp}"

    class Meta:
        ordering = ["-timestamp"]

    # Approve the activity
    def approve_activity(self):
        # Check auto-approval criteria
        if self.like_count >= 3 and self.dislike_count < 3:
            self.is_approved = True
        self.save()

    # Post to BlueSky
    def post_to_bluesky(self, bluesky_service):
        if not self.is_approved:
            raise ValueError("Activity must be approved before posting to BlueSky.")

        try:
            post_data = f"{self.title}\n\n{self.description}"
            # If image exists, include it
            if self.image:
                bluesky_service.post_with_image(text=post_data, image_path=self.image.path)
            else:
                bluesky_service.post_text(text=post_data)

            # Mark activity as posted
            self.is_posted_to_bluesky = True
            self.save()
            return True
        except Exception as e:
            print(e)


class Badge(models.Model):
    BADGE_TYPES = [
        ("automatic", "Automatic"),
        ("manual", "Manual"),
    ]

    title = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.ImageField(upload_to="badges/", blank=True, null=True)
    type = models.CharField(max_length=10, choices=BADGE_TYPES, default="automatic")
    criteria = models.JSONField(blank=True, null=True)  # For automatic badges
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    awarded_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name="awarded_badges",
        on_delete=models.SET_NULL,
    )
    awarded_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.badge.title}"


class Post(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True, max_length=255)
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    image = models.ImageField(upload_to="blog_posts")
    comments = GenericRelation("comments.Comment")

    class Meta:
        db_table = "blog_post"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("post_detail", kwargs={"slug": self.slug})


class PRAnalysisReport(models.Model):
    pr_link = models.URLField()
    issue_link = models.URLField()
    priority_alignment_score = models.IntegerField()
    revision_score = models.IntegerField()
    recommendations = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.pr_link


@receiver(post_save, sender=Post)
def verify_file_upload(sender, instance, **kwargs):
    from django.core.files.storage import default_storage

    print("Verifying file upload...")
    print(f"Default storage backend: {default_storage.__class__.__name__}")
    if instance.image:
        print(f"Checking if image '{instance.image.name}' exists in the storage backend...")
        if not default_storage.exists(instance.image.name):
            print(f"Image '{instance.image.name}' was not uploaded to the storage backend.")
            raise ValidationError(
                f"Image '{instance.image.name}' was not uploaded to the storage backend."
            )


class Repo(models.Model):
    project = models.ForeignKey(Project, related_name="repos", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(null=True, blank=True)  # Made nullable for optional descriptions
    repo_url = models.URLField(unique=True)
    homepage_url = models.URLField(null=True, blank=True)
    is_main = models.BooleanField(default=False)
    is_wiki = models.BooleanField(default=False)
    stars = models.IntegerField(default=0)
    forks = models.IntegerField(default=0)
    open_issues = models.IntegerField(default=0)
    tags = models.ManyToManyField("Tag", blank=True)
    last_updated = models.DateTimeField(null=True, blank=True)
    total_issues = models.IntegerField(default=0)
    # rename this to repo_visit_count and make sure the github badge works with this
    repo_visit_count = models.IntegerField(default=0)
    watchers = models.IntegerField(default=0)
    open_pull_requests = models.IntegerField(default=0)
    primary_language = models.CharField(max_length=50, null=True, blank=True)
    license = models.CharField(max_length=100, null=True, blank=True)
    last_commit_date = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)
    network_count = models.IntegerField(default=0)
    subscribers_count = models.IntegerField(default=0)
    closed_issues = models.IntegerField(default=0)
    size = models.IntegerField(default=0)
    commit_count = models.IntegerField(default=0)
    release_name = models.CharField(max_length=255, null=True, blank=True)
    release_datetime = models.DateTimeField(null=True, blank=True)
    logo_url = models.URLField(null=True, blank=True)
    contributor_count = models.IntegerField(default=0)
    contributor = models.ManyToManyField(Contributor, related_name="repos", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            # Replace dots with dashes and limit length
            base_slug = base_slug.replace(".", "-")
            if len(base_slug) > 50:
                base_slug = base_slug[:50]
            # Ensure we have a valid slug
            if not base_slug:
                base_slug = f"repo-{int(time.time())}"

            unique_slug = base_slug
            counter = 1
            while Repo.objects.filter(slug=unique_slug).exists():
                suffix = f"-{counter}"
                # Make sure base_slug + suffix doesn't exceed 50 chars
                if len(base_slug) + len(suffix) > 50:
                    base_slug = base_slug[: 50 - len(suffix)]
                unique_slug = f"{base_slug}{suffix}"
                counter += 1

            self.slug = unique_slug
        super(Repo, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.project.name}/{self.name}"


class ContributorStats(models.Model):
    contributor = models.ForeignKey(Contributor, on_delete=models.CASCADE, related_name="stats")
    repo = models.ForeignKey(Repo, on_delete=models.CASCADE, related_name="stats")

    # This will represent either a specific day or the first day of a month.
    date = models.DateField()

    # Store counts
    commits = models.PositiveIntegerField(default=0)
    issues_opened = models.PositiveIntegerField(default=0)
    issues_closed = models.PositiveIntegerField(default=0)
    pull_requests = models.PositiveIntegerField(default=0)
    comments = models.PositiveIntegerField(default=0)

    # "day" for daily entries, "month" for monthly entries
    granularity = models.CharField(
        max_length=10, choices=[("day", "Day"), ("month", "Month")], default="day"
    )

    class Meta:
        # You can't have two different stats for the same date+granularity
        unique_together = ("contributor", "repo", "date", "granularity")

    def __str__(self):
        return (
            f"{self.contributor.name} in {self.repo.name} " f"on {self.date} [{self.granularity}]"
        )


class Challenge(models.Model):
    CHALLENGE_TYPE_CHOICES = [
        ("single", "Single User"),
        ("team", "Team"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField()
    challenge_type = models.CharField(
        max_length=10, choices=CHALLENGE_TYPE_CHOICES, default="single"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    participants = models.ManyToManyField(
        User, related_name="user_challenges", blank=True
    )  # For single users
    team_participants = models.ManyToManyField(
        Organization, related_name="team_challenges", blank=True
    )  # For team challenges
    points = models.IntegerField(default=0)  # Points for completing the challenge
    progress = models.IntegerField(default=0)  # Progress in percentage
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title
