from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import User, UserRole


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    role = serializers.ChoiceField(choices=UserRole.choices, required=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'password', 'role', 'phone_number')
        read_only_fields = ('id',)

    def validate_email(self, value):
        normalized = value.lower().strip()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate_role(self, value):
        if value == UserRole.ADMIN:
            raise serializers.ValidationError("Admin accounts cannot be self-registered.")
        if value not in (UserRole.STUDENT, UserRole.ISSUER, UserRole.RECRUITER):
            raise serializers.ValidationError(f"Invalid role: {value}")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(
            password=password,
            **validated_data
        )
        return user

    def to_representation(self, instance):
        return {
            'id': str(instance.id),
            'email': instance.email,
            'role': instance.role,
        }


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom login serializer that adds role and user_id claims to JWT tokens
    and returns { access, refresh, role } per API_SPECIFICATION.md.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Custom claims
        token['user_id'] = str(user.id)
        token['role'] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['role'] = self.user.role
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)

    def validate(self, attrs):
        self.token = attrs['refresh']
        return attrs

    def save(self, **kwargs):
        try:
            token = RefreshToken(self.token)
            token.blacklist()
        except Exception as exc:
            raise serializers.ValidationError({"refresh": f"Invalid or expired refresh token: {exc}"})


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'role', 'phone_number', 'is_active', 'created_at', 'profile')
        read_only_fields = ('id', 'role', 'created_at')

    def get_profile(self, obj):
        # In later phases, links to StudentProfile, IssuerProfile, or RecruiterProfile
        return None
