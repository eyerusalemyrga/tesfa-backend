from unittest.mock import patch, MagicMock
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APITestCase
from users.models import User, ADMIN, HEALTH_PROFESSIONAL
from conversations.models import Message
from api import tesfa_data


def tesfa_json_response():
    response = MagicMock(status_code=200, headers={'Content-Type': 'application/json'})
    response.json.return_value = {
        "status": "success",
        "result": {
            "status": "success",
            "analysis_text": "Sudan faces high displacement risk.",
            "metrics": {"conflict_count": 3},
            "top_conflicts": [
                {"country_a": "Sudan", "country_b": "South Sudan", "year": 2023, "predicted_risk_score": 18},
                {"country_a": "Ethiopia", "country_b": "Eritrea", "year": 1998, "predicted_risk_score": 15},
            ],
            "chart": {"chart_type": "bar", "labels": ["Sudan vs South Sudan (2023)", "Ethiopia vs Eritrea (1998)"], "values": [18, 15]},
        },
    }
    return response


def tesfa_text_response():
    return MagicMock(status_code=200, headers={'Content-Type': 'text/plain; charset=utf-8'}, text="Hi! How can I help you today?\n")


class TesfaAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            email='admin@tesfa.org', password='StrongPass123!', first_name='Ad', last_name='Min',
            phone_number='0700000000', user_type=ADMIN,
        )

    def register_and_login(self, email='doc@tesfa.org', phone='0711111111', country='Kenya'):
        response = self.client.post('/api/register/', {
            'email': email, 'password': 'StrongPass123!', 'first_name': 'Doc', 'last_name': 'Tor',
            'phone_number': phone, 'country': country, 'user_type': ADMIN,
        })
        self.assertEqual(response.status_code, 201)
        return self.login(email)

    def login(self, email):
        response = self.client.post('/api/login/', {'email': email, 'password': 'StrongPass123!'})
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response.data['user']

    def test_register_always_creates_health_professional(self):
        user = self.register_and_login()
        self.assertEqual(user['user_type'], HEALTH_PROFESSIONAL)

    def test_only_admin_can_manage_users(self):
        self.register_and_login()
        self.assertEqual(self.client.get('/api/users/').status_code, 403)
        self.login('admin@tesfa.org')
        response = self.client.get('/api/users/', {'user_type': HEALTH_PROFESSIONAL})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_profile_cannot_change_role(self):
        self.register_and_login()
        response = self.client.patch('/api/profile/', {'user_type': ADMIN, 'organization': 'MSF'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user_type'], HEALTH_PROFESSIONAL)
        self.assertEqual(response.data['organization'], 'MSF')

    @patch('api.tesfa_client.requests.post')
    def test_query_saves_conversation_countries_and_chart(self, mock_post):
        mock_post.return_value = tesfa_json_response()
        self.register_and_login()
        response = self.client.post('/api/query/', {'query': 'Show stats for Sudan', 'region': 'Sudan'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['countries'], ['Sudan', 'South Sudan', 'Ethiopia', 'Eritrea'])
        self.assertEqual(response.data['chart']['values'], [18, 15])
        self.assertEqual(mock_post.call_args.kwargs['json'], {'query': 'Show stats for Sudan', 'region': 'Sudan', 'conflict_type': None})

        conversation_id = response.data['conversation']
        mock_post.return_value = tesfa_text_response()
        response = self.client.post('/api/query/', {'query': 'thanks', 'conversation_id': conversation_id})
        self.assertEqual(response.data['content'], 'Hi! How can I help you today?')
        self.assertIsNone(response.data['chart'])

        detail = self.client.get(f'/api/conversations/{conversation_id}/')
        self.assertEqual(len(detail.data['messages']), 4)

        charts = self.client.get('/api/charts/', {'country': 'sudan'})
        self.assertEqual(len(charts.data), 1)
        self.assertEqual(charts.data[0]['question'], 'Show stats for Sudan')

    @patch('api.tesfa_client.requests.post')
    def test_query_tesfa_unavailable(self, mock_post):
        mock_post.return_value = MagicMock(status_code=503, headers={'Content-Type': 'application/json'})
        mock_post.return_value.json.return_value = {"detail": "The AI service is busy right now."}
        self.register_and_login()
        response = self.client.post('/api/query/', {'query': 'risk in Sudan'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Message.objects.count(), 0)

    @patch('api.tesfa_client.requests.post')
    def test_users_cannot_see_others_conversations(self, mock_post):
        mock_post.return_value = tesfa_text_response()
        self.register_and_login()
        conversation_id = self.client.post('/api/query/', {'query': 'hello'}).data['conversation']
        self.register_and_login('doc2@tesfa.org', '0722222222')
        self.assertEqual(self.client.get(f'/api/conversations/{conversation_id}/').status_code, 404)
        self.assertEqual(self.client.post('/api/query/', {'query': 'hi', 'conversation_id': conversation_id}).status_code, 404)

    def test_password_reset_with_otp(self):
        self.register_and_login()
        self.client.credentials()
        self.client.post('/api/forgot-password/', {'email': 'doc@tesfa.org'})
        otp = mail.outbox[0].body.split(': ')[1][:4]
        self.assertEqual(self.client.post('/api/reset-password/', {'email': 'doc@tesfa.org', 'password': 'NewPass456!x'}).status_code, 400)
        self.assertEqual(self.client.post('/api/verify-otp/', {'email': 'doc@tesfa.org', 'otp': otp}).status_code, 200)
        self.assertEqual(self.client.post('/api/reset-password/', {'email': 'doc@tesfa.org', 'password': 'NewPass456!x'}).status_code, 200)
        self.assertEqual(self.client.post('/api/login/', {'email': 'doc@tesfa.org', 'password': 'NewPass456!x'}).status_code, 200)


COUNTRY = {
    'id': 1, 'name': 'Ukraine', 'conflict_count': 2, 'avg_risk_score': 12.5, 'total_civilian_deaths': 1000,
    'total_refugees_millions': 3.5, 'total_economic_loss_usd_billions': 200.0,
}


class TesfaDataAPITests(APITestCase):
    """Countries and graphs come from Tesfa AI's database; the queries are mocked here."""

    def setUp(self):
        user = User.objects.create_user(
            email='doc@tesfa.org', password='StrongPass123!', first_name='Doc', last_name='Tor', phone_number='0711111111',
        )
        self.client.force_authenticate(user)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/countries/').status_code, 401)
        self.assertEqual(self.client.get('/api/graphs/').status_code, 401)

    @patch.object(tesfa_data, 'list_countries', return_value=[COUNTRY])
    def test_list_countries(self, mock_list):
        response = self.client.get('/api/countries/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['name'], 'Ukraine')

    @patch.object(tesfa_data, 'get_country')
    def test_country_detail(self, mock_get):
        mock_get.return_value = None
        self.assertEqual(self.client.get('/api/countries/99/').status_code, 404)
        self.assertEqual(self.client.get('/api/countries/1/', {'limit': 'abc'}).status_code, 400)

        mock_get.return_value = {**COUNTRY, 'conflicts': [{
            'id': 7, 'country_a': 'Ukraine', 'country_b': 'Russia', 'conflict_type': 'War', 'year': 2022,
            'duration_days': 900, 'civilian_deaths': 1000, 'military_deaths_a': 10, 'military_deaths_b': 20,
            'economic_loss_usd_billions': 200.0, 'refugees_millions': 3.5, 'outcome': 'Stalemate',
            'latitude': 48.3, 'longitude': 31.1, 'predicted_risk_score': 15.0, 'risk_category': 'HIGH',
            'predicted_postwar_consequence': 'Health system strain', 'evidence_reference_links': [{'title': 'WHO', 'url': 'https://who.int'}],
        }]}
        response = self.client.get('/api/countries/1/', {'limit': 1000})
        self.assertEqual(response.status_code, 200)
        mock_get.assert_called_with(1, 500)
        self.assertEqual(response.data['conflicts'][0]['country_b'], 'Russia')

    @patch.object(tesfa_data, 'get_graphs')
    def test_graphs(self, mock_graphs):
        chart = {'chart_type': 'line', 'title': 'Conflicts per year', 'labels': [2021, 2022], 'values': [1.0, 1.0]}
        mock_graphs.return_value = {
            'country': 'Ukraine',
            'summary': {k: v for k, v in COUNTRY.items() if k not in ('id', 'name')} | {'conflict_count': 2},
            'charts': {'conflicts_per_year': chart},
            'map_points': [],
        }
        response = self.client.get('/api/graphs/', {'country': 'Ukraine'})
        self.assertEqual(response.status_code, 200)
        mock_graphs.assert_called_with('Ukraine')
        self.assertEqual(response.data['charts']['conflicts_per_year']['labels'], ['2021', '2022'])
