from django.conf import settings
from django.db import models


ROLE_CHOICES = [
    ('user', 'User'),
    ('assistant', 'Assistant'),
]

class Conversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or f"Conversation {self.pk}"

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    region = models.CharField(max_length=100, blank=True)
    conflict_type = models.CharField(max_length=100, blank=True)
    # Data returned by Tesfa AI when the user asks for details (numbers, charts, sources).
    metrics = models.JSONField(null=True, blank=True)
    top_conflicts = models.JSONField(null=True, blank=True)
    chart = models.JSONField(null=True, blank=True)
    countries = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
