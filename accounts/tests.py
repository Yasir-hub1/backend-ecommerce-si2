"""Tests for the append-only bitácora (audit log)."""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Bitacora, BitacoraAction, Role, User
from accounts.services.bitacora import log_action, sanitize_payload


class BitacoraServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='admin@example.com',
            password='Segura1234',
            first_name='Ana',
            last_name='Admin',
            role=Role.ADMIN,
        )

    def test_log_action_stores_user_action_and_date(self):
        log_action(
            action=BitacoraAction.CREATE,
            module='catalog',
            description='Creó producto #1',
            user=self.user,
            resource='products',
            object_id='1',
        )
        entry = Bitacora.objects.get()
        self.assertEqual(entry.user_id, self.user.id)
        self.assertEqual(entry.user_email, 'admin@example.com')
        self.assertEqual(entry.action, BitacoraAction.CREATE)
        self.assertEqual(entry.module, 'catalog')
        self.assertIsNotNone(entry.created_at)

    def test_sanitize_redacts_passwords(self):
        cleaned = sanitize_payload({'email': 'a@b.com', 'password': 'secret', 'nested': {'token': 'abc'}})
        self.assertEqual(cleaned['password'], '[redacted]')
        self.assertEqual(cleaned['nested']['token'], '[redacted]')
        self.assertEqual(cleaned['email'], 'a@b.com')


class BitacoraApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='admin@example.com',
            password='Segura1234',
            first_name='Ana',
            last_name='Admin',
            role=Role.ADMIN,
            is_staff=True,
        )
        self.cashier = User.objects.create_user(
            email='caja@example.com',
            password='Segura1234',
            first_name='Carlos',
            last_name='Caja',
            role=Role.CASHIER,
        )

    def test_register_writes_bitacora(self):
        response = self.client.post(
            '/api/v1/auth/register/',
            {
                'email': 'cliente@example.com',
                'password': 'Segura1234',
                'password_confirm': 'Segura1234',
                'first_name': 'Luis',
                'last_name': 'Cliente',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        entry = Bitacora.objects.get(action=BitacoraAction.REGISTER)
        self.assertEqual(entry.module, 'accounts')
        self.assertEqual(entry.user_email, 'cliente@example.com')
        self.assertIn('Registró', entry.description)
        body = entry.metadata.get('body', {})
        self.assertEqual(body.get('password'), '[redacted]')
        self.assertEqual(body.get('password_confirm'), '[redacted]')

    def test_login_success_and_failure_are_recorded(self):
        ok = self.client.post(
            '/api/v1/auth/login/',
            {'email': 'admin@example.com', 'password': 'Segura1234'},
            format='json',
        )
        self.assertEqual(ok.status_code, 200)
        login = Bitacora.objects.get(action=BitacoraAction.LOGIN)
        self.assertEqual(login.user_id, self.admin.id)

        fail = self.client.post(
            '/api/v1/auth/login/',
            {'email': 'admin@example.com', 'password': 'wrong-password'},
            format='json',
        )
        self.assertEqual(fail.status_code, 401)
        failed = Bitacora.objects.get(action=BitacoraAction.LOGIN_FAILED)
        self.assertEqual(failed.user_email, 'admin@example.com')

    def test_creating_a_brand_records_catalog_action(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            '/api/v1/brands/',
            {'name': 'Veta'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        entry = Bitacora.objects.get(module='catalog', action=BitacoraAction.CREATE)
        self.assertEqual(entry.user_id, self.admin.id)
        self.assertEqual(entry.resource, 'brands')
        self.assertEqual(entry.object_id, str(response.data['id']))
        self.assertIn('marca', entry.description.lower())

    def test_get_requests_are_not_recorded(self):
        self.client.force_authenticate(self.admin)
        self.client.get('/api/v1/brands/')
        self.assertFalse(Bitacora.objects.exists())

    def test_admin_can_list_bitacora_cashier_cannot(self):
        log_action(
            action=BitacoraAction.UPDATE,
            module='orders',
            description='Actualizó orden #9',
            user=self.admin,
        )
        self.client.force_authenticate(self.admin)
        allowed = self.client.get('/api/v1/bitacora/')
        self.assertEqual(allowed.status_code, 200)
        self.assertGreaterEqual(allowed.data['count'], 1)

        self.client.force_authenticate(self.cashier)
        denied = self.client.get('/api/v1/bitacora/')
        self.assertEqual(denied.status_code, 403)
