import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token


@pytest.mark.django_db
class TestAuthentication:
    def setup_method(self):
        self.client = APIClient()
        self.username = "testuser"
        self.password = "Secr3tPassw0rd!"
        self.user = User.objects.create_user(
            username=self.username,
            password=self.password,
            email="testuser@example.com"
        )

    def test_obtain_auth_token_success(self):
        url = reverse('assets:api-token-auth')
        response = self.client.post(url, {
            'username': self.username,
            'password': self.password
        })
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'token' in data
        token = Token.objects.get(user=self.user)
        assert data['token'] == token.key

    def test_obtain_auth_token_invalid_credentials(self):
        url = reverse('assets:api-token-auth')
        response = self.client.post(url, {
            'username': self.username,
            'password': 'wrongpassword'
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'non_field_errors' in response.json()
