from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    github_access_token = models.TextField(null=True, blank=True)
    github_username = models.CharField(max_length=200, null=True, blank=True)
    
    # Subscription
    PLAN_FREE = "free"
    PLAN_PRO = "pro"
    PLAN_TEAM = "team"
    PLAN_CHOICES = [(PLAN_FREE, "Free"), (PLAN_PRO, "Pro"), (PLAN_TEAM, "Team")]
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default=PLAN_FREE)
    meetings_this_month = models.PositiveIntegerField(default=0)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        verbose_name = "User"

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def can_upload_meeting(self):
        if self.plan == self.PLAN_FREE and self.meetings_this_month >= 10:
            return False
        return True
