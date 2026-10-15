from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from users.models import User, HEALTH_PROFESSIONAL
from conversations.models import Conversation, Message


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, validators=[validate_password])
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id", "first_name", "last_name", "phone_number", "email", "password",
            "user_type", "country", "organization", "image", "is_active", "date_joined"
        ]
        read_only_fields = ["id", "date_joined"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class ProfileSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        read_only_fields = ["id", "date_joined", "user_type", "is_active"]


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
        validators=[validate_password]
    )
    phone_number = serializers.CharField(
        validators=[UniqueValidator(queryset=User.objects.all(), message="Phone number already registered.")]
    )
    email = serializers.EmailField(
        validators=[UniqueValidator(queryset=User.objects.all(), message="Email already registered.")]
    )

    class Meta:
        model = User
        fields = [
            "id", "first_name", "last_name", "phone_number", "email", "password",
            "country", "organization", "image", "date_joined"
        ]
        read_only_fields = ["id", "date_joined"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, user_type=HEALTH_PROFESSIONAL, **validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data["email"], password=data["password"])
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        data["user"] = user
        return data


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return value


class VerifyCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=4)

    def validate(self, data):
        try:
            user = User.objects.get(email=data["email"])
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid email")
        cached_otp = cache.get(f"otp_{user.id}")
        if not cached_otp or str(cached_otp) != str(data["otp"]):
            raise serializers.ValidationError("Invalid or expired OTP")
        cache.set(f"otp_verified_{user.id}", True, timeout=600)
        return data


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate(self, data):
        try:
            user = User.objects.get(email=data["email"])
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        if not cache.get(f"otp_verified_{user.id}"):
            raise serializers.ValidationError("OTP not verified. Please verify OTP before resetting password.")
        return data

    def save(self, **kwargs):
        user = User.objects.get(email=self.validated_data["email"])
        user.set_password(self.validated_data["password"])
        user.save()
        cache.delete(f"otp_{user.id}")
        cache.delete(f"otp_verified_{user.id}")
        return user


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = [
            "id", "conversation", "role", "content", "region", "conflict_type",
            "metrics", "top_conflicts", "chart", "countries", "created_at"
        ]
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "user", "title", "created_at", "updated_at"]
        read_only_fields = ["id", "user", "created_at", "updated_at"]


class ConversationDetailSerializer(ConversationSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ["messages"]


class QuerySerializer(serializers.Serializer):
    query = serializers.CharField()
    region = serializers.CharField(required=False, allow_blank=True)
    conflict_type = serializers.CharField(required=False, allow_blank=True)
    conversation_id = serializers.IntegerField(required=False, help_text="Leave out to start a new conversation.")


def question_for(answer):
    """The user's question that a Tesfa AI answer replied to."""
    question = answer.conversation.messages.filter(role='user', created_at__lte=answer.created_at).last()
    return question.content if question else None


class ChartSerializer(serializers.ModelSerializer):
    question = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ["id", "conversation", "question", "countries", "chart", "metrics", "top_conflicts", "created_at"]

    def get_question(self, obj) -> str | None:
        return question_for(obj)


class CountrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    conflict_count = serializers.IntegerField()
    avg_risk_score = serializers.FloatField()
    total_civilian_deaths = serializers.IntegerField()
    total_refugees_millions = serializers.FloatField()
    total_economic_loss_usd_billions = serializers.FloatField()


class ConflictSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    country_a = serializers.CharField()
    country_b = serializers.CharField()
    conflict_type = serializers.CharField()
    year = serializers.IntegerField()
    duration_days = serializers.IntegerField(allow_null=True)
    civilian_deaths = serializers.IntegerField(allow_null=True)
    military_deaths_a = serializers.IntegerField(allow_null=True)
    military_deaths_b = serializers.IntegerField(allow_null=True)
    economic_loss_usd_billions = serializers.FloatField(allow_null=True)
    refugees_millions = serializers.FloatField(allow_null=True)
    outcome = serializers.CharField(allow_null=True)
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    predicted_risk_score = serializers.FloatField(allow_null=True)
    risk_category = serializers.CharField(allow_null=True)
    predicted_postwar_consequence = serializers.CharField(allow_null=True)
    evidence_reference_links = serializers.JSONField(allow_null=True)


class CountryDetailSerializer(CountrySerializer):
    conflicts = ConflictSerializer(many=True)


class ChartDataSerializer(serializers.Serializer):
    chart_type = serializers.CharField()
    title = serializers.CharField()
    labels = serializers.ListField(child=serializers.CharField())
    values = serializers.ListField(child=serializers.FloatField())


class GraphSummarySerializer(serializers.Serializer):
    conflict_count = serializers.IntegerField()
    avg_risk_score = serializers.FloatField()
    total_civilian_deaths = serializers.IntegerField()
    total_refugees_millions = serializers.FloatField()
    total_economic_loss_usd_billions = serializers.FloatField()


class MapPointSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    country_a = serializers.CharField()
    country_b = serializers.CharField()
    year = serializers.IntegerField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    predicted_risk_score = serializers.FloatField(allow_null=True)
    risk_category = serializers.CharField(allow_null=True)


class GraphsSerializer(serializers.Serializer):
    country = serializers.CharField(allow_null=True)
    summary = GraphSummarySerializer()
    charts = serializers.DictField(child=ChartDataSerializer())
    map_points = MapPointSerializer(many=True)

