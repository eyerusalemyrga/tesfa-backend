from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'first_name', 'last_name', 'user_type', 'country', 'is_active', 'date_joined')
    list_filter = ('user_type', 'is_active', 'country')
    search_fields = ('email', 'first_name', 'last_name', 'phone_number')
