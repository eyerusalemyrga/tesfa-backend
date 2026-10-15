from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


ADMIN = 'Admin'
HEALTH_PROFESSIONAL = 'Health Professional'

USER_TYPE_CHOICES = [
    (ADMIN, 'Admin'),
    (HEALTH_PROFESSIONAL, 'Health Professional'),
]

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **all_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **all_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **all_fields):
        all_fields.setdefault('user_type', ADMIN)
        all_fields.setdefault('is_staff', True)
        all_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **all_fields)

class User(AbstractBaseUser, PermissionsMixin):
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    first_name = models.CharField(_("First Name"), max_length=30, blank=False)
    last_name = models.CharField(_("Last Name"), max_length=30, blank=False)
    email = models.EmailField(_("Email Address"), max_length=255, unique=True)
    phone_number = models.CharField(_("Phone Number"), max_length=20, unique=True)
    user_type = models.CharField(
        _("User Type"),
        max_length=30,
        choices=USER_TYPE_CHOICES,
        default=HEALTH_PROFESSIONAL,
    )
    country = models.CharField(_("Country"), max_length=100, blank=True)
    organization = models.CharField(_("Organization"), max_length=150, blank=True)
    image = models.ImageField(upload_to='profile_images/', blank=True, null=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone_number', 'first_name', 'last_name']

    @property
    def is_admin(self):
        return self.user_type == ADMIN

    @property
    def is_health_professional(self):
        return self.user_type == HEALTH_PROFESSIONAL

    def __str__(self):
        return self.email
