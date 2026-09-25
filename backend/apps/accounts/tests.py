from io import StringIO
from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import User, UserRole


class RegistrationTests(APITestCase):
    def setUp(self):
        self.register_url = reverse('auth_register')

    def test_student_registration_success(self):
        payload = {
            'email': 'student@educhain.local',
            'password': 'StrongPassword123!',
            'role': UserRole.STUDENT,
            'phone_number': '+919876543210'
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['email'], 'student@educhain.local')
        self.assertEqual(response.data['role'], UserRole.STUDENT)
        self.assertIn('id', response.data)

        # Confirm saved in DB with hashed password
        user = User.objects.get(email='student@educhain.local')
        self.assertTrue(user.check_password('StrongPassword123!'))
        self.assertEqual(user.role, UserRole.STUDENT)
        self.assertEqual(user.phone_number, '+919876543210')

    def test_issuer_registration_success(self):
        payload = {
            'email': 'issuer@univ.edu',
            'password': 'StrongPassword123!',
            'role': UserRole.ISSUER,
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['role'], UserRole.ISSUER)

    def test_recruiter_registration_success(self):
        payload = {
            'email': 'recruiter@techcorp.com',
            'password': 'StrongPassword123!',
            'role': UserRole.RECRUITER,
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['role'], UserRole.RECRUITER)

    def test_admin_registration_rejected(self):
        """Admin accounts must NOT be self-registrable via API."""
        payload = {
            'email': 'malicious_admin@educhain.local',
            'password': 'StrongPassword123!',
            'role': UserRole.ADMIN,
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')
        self.assertIn('Admin accounts cannot be self-registered', response.data['detail'])

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            email='existing@educhain.local',
            password='Password123!',
            role=UserRole.STUDENT
        )
        payload = {
            'email': 'existing@educhain.local',
            'password': 'AnotherPassword123!',
            'role': UserRole.STUDENT,
        }
        response = self.client.post(self.register_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 'VALIDATION_ERROR')


class AuthenticationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='student@educhain.local',
            password='CorrectPassword123!',
            role=UserRole.STUDENT
        )
        self.login_url = reverse('auth_login')
        self.refresh_url = reverse('auth_refresh')
        self.logout_url = reverse('auth_logout')
        self.me_url = reverse('user_me')

    def test_login_success(self):
        response = self.client.post(self.login_url, {
            'email': 'student@educhain.local',
            'password': 'CorrectPassword123!'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['role'], UserRole.STUDENT)

        # Inspect token claims per AUTHENTICATION.md
        access_token = AccessToken(response.data['access'])
        self.assertEqual(str(access_token['user_id']), str(self.user.id))
        self.assertEqual(access_token['role'], UserRole.STUDENT)

    def test_login_invalid_credentials(self):
        response = self.client.post(self.login_url, {
            'email': 'student@educhain.local',
            'password': 'WrongPassword!'
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'UNAUTHENTICATED')

    def test_token_refresh(self):
        login_resp = self.client.post(self.login_url, {
            'email': 'student@educhain.local',
            'password': 'CorrectPassword123!'
        }, format='json')
        refresh_token = login_resp.data['refresh']

        refresh_resp = self.client.post(self.refresh_url, {
            'refresh': refresh_token
        }, format='json')

        self.assertEqual(refresh_resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_resp.data)

    def test_logout_blacklists_refresh_token(self):
        login_resp = self.client.post(self.login_url, {
            'email': 'student@educhain.local',
            'password': 'CorrectPassword123!'
        }, format='json')
        access_token = login_resp.data['access']
        refresh_token = login_resp.data['refresh']

        # Logout with Bearer access token and refresh token in body
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        logout_resp = self.client.post(self.logout_url, {
            'refresh': refresh_token
        }, format='json')
        self.assertEqual(logout_resp.status_code, status.HTTP_205_RESET_CONTENT)

        # Attempting to refresh with blacklisted token must fail
        self.client.credentials()  # Clear auth headers
        reuse_resp = self.client.post(self.refresh_url, {
            'refresh': refresh_token
        }, format='json')
        self.assertEqual(reuse_resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(reuse_resp.data['code'], 'REFRESH_INVALID')


class PermissionsAndProfileTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email='student@educhain.local',
            password='Password123!',
            role=UserRole.STUDENT
        )
        self.issuer = User.objects.create_user(
            email='issuer@educhain.local',
            password='Password123!',
            role=UserRole.ISSUER
        )
        self.admin = User.objects.create_superuser(
            email='admin@educhain.local',
            password='Password123!'
        )
        self.me_url = reverse('user_me')

    def test_unauthenticated_request_rejected(self):
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'UNAUTHENTICATED')

    def test_invalid_token_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid.token.value')
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 'TOKEN_EXPIRED')

    def test_authenticated_user_can_access_own_profile(self):
        refresh = RefreshToken.for_user(self.student)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'student@educhain.local')
        self.assertEqual(response.data['role'], UserRole.STUDENT)
        self.assertEqual(str(response.data['id']), str(self.student.id))

    def test_role_permission_classes(self):
        from apps.accounts.permissions import IsAdmin, IsIssuer, IsStudent

        class DummyView:
            pass

        class MockRequest:
            def __init__(self, user):
                self.user = user

        admin_perm = IsAdmin()
        issuer_perm = IsIssuer()
        student_perm = IsStudent()

        # Admin user
        self.assertTrue(admin_perm.has_permission(MockRequest(self.admin), DummyView()))
        self.assertFalse(issuer_perm.has_permission(MockRequest(self.admin), DummyView()))
        self.assertFalse(student_perm.has_permission(MockRequest(self.admin), DummyView()))

        # Student user
        self.assertFalse(admin_perm.has_permission(MockRequest(self.student), DummyView()))
        self.assertTrue(student_perm.has_permission(MockRequest(self.student), DummyView()))


class CreateAdminCommandTests(APITestCase):
    def test_create_admin_command(self):
        out = StringIO()
        call_command(
            'create_admin',
            email='newadmin@educhain.local',
            password='AdminPassword123!',
            phone='+1234567890',
            stdout=out
        )
        self.assertIn('Successfully created ADMIN user', out.getvalue())

        admin_user = User.objects.get(email='newadmin@educhain.local')
        self.assertEqual(admin_user.role, UserRole.ADMIN)
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.check_password('AdminPassword123!'))
