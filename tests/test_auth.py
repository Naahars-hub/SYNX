import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import get_db_connection, init_db

class TestAuthEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_auth_config(self):
        res = self.client.get('/api/auth/config')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('google_client_id', data)
        self.assertTrue(data.get('demo_enabled'))

    def test_demo_login_and_me_lifecycle(self):
        login_payload = {
            'name': 'Inspector Priya Sharma',
            'email': 'priya.sharma@legalmetrology.gov.in',
            'role': 'Senior Legal Metrology Officer',
            'department': 'Legal Metrology Enforcement Division'
        }
        res = self.client.post('/api/auth/demo-login', json=login_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('token', data)
        token = data['token']
        user = data['user']
        self.assertEqual(user['email'], 'priya.sharma@legalmetrology.gov.in')
        self.assertEqual(user['name'], 'Inspector Priya Sharma')

        headers = {'Authorization': f'Bearer {token}'}
        res_me = self.client.get('/api/auth/me', headers=headers)
        self.assertEqual(res_me.status_code, 200)
        me_data = res_me.json()
        self.assertEqual(me_data['user']['email'], 'priya.sharma@legalmetrology.gov.in')

        res_unauth = self.client.get('/api/auth/me')
        self.assertEqual(res_unauth.status_code, 401)

        res_logout = self.client.post('/api/auth/logout', headers=headers)
        self.assertEqual(res_logout.status_code, 200)

        res_after = self.client.get('/api/auth/me', headers=headers)
        self.assertEqual(res_after.status_code, 401)

    def test_audit_records_inspector_identity(self):
        res = self.client.post('/api/auth/demo-login', json={
            'name': 'Officer Vikram Verma',
            'email': 'vikram.verma@legalmetrology.gov.in'
        })
        token = res.json()['token']

        headers = {'Authorization': f'Bearer {token}'}
        audit_res = self.client.post(
            '/api/audit',
            data={
                'sample_filenames': 'real_haldiram_snack.jpg',
                'calibration_mode': 'dimensions',
                'package_type': 'flexible_pouch',
                'package_width_mm': '160.0',
                'package_height_mm': '220.0'
            },
            headers=headers
        )
        self.assertEqual(audit_res.status_code, 200)
        audit_id = audit_res.json()['audit_id']

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT inspector_name, inspector_email FROM inspections WHERE audit_id = ?;', (audit_id,))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['inspector_name'], 'Officer Vikram Verma')
            self.assertEqual(row['inspector_email'], 'vikram.verma@legalmetrology.gov.in')

    def test_history_scoped_to_authenticated_officer(self):
        # 1. Login as Officer A
        res_a = self.client.post('/api/auth/demo-login', json={
            'name': 'Officer Anita Desai',
            'email': 'anita.desai@legalmetrology.gov.in'
        })
        token_a = res_a.json()['token']
        headers_a = {'Authorization': f'Bearer {token_a}'}

        # 2. Officer A performs an audit
        audit_res = self.client.post(
            '/api/audit',
            data={
                'sample_filenames': 'real_haldiram_snack.jpg',
                'calibration_mode': 'dimensions',
                'package_type': 'flexible_pouch',
                'package_width_mm': '160.0',
                'package_height_mm': '220.0'
            },
            headers=headers_a
        )
        self.assertEqual(audit_res.status_code, 200)
        audit_id_a = audit_res.json()['audit_id']

        # 3. Officer A queries /api/history (defaults to personal scope)
        hist_a = self.client.get('/api/history', headers=headers_a)
        self.assertEqual(hist_a.status_code, 200)
        records_a = hist_a.json()
        self.assertTrue(len(records_a) > 0)
        for r in records_a:
            self.assertEqual(r['inspector_email'], 'anita.desai@legalmetrology.gov.in')

        # 4. Officer B logs in (has 0 audits)
        res_b = self.client.post('/api/auth/demo-login', json={
            'name': 'New Officer Suresh',
            'email': 'suresh.new@legalmetrology.gov.in'
        })
        token_b = res_b.json()['token']
        headers_b = {'Authorization': f'Bearer {token_b}'}

        # Officer B queries history without scope=all -> should see 0 records
        hist_b = self.client.get('/api/history', headers=headers_b)
        self.assertEqual(hist_b.status_code, 200)
        self.assertEqual(len(hist_b.json()), 0)

        # Officer B explicitly queries scope=all -> sees all department records
        hist_b_all = self.client.get('/api/history?scope=all', headers=headers_b)
        self.assertEqual(hist_b_all.status_code, 200)
        self.assertTrue(len(hist_b_all.json()) > 0)
        self.assertTrue(any(r['audit_id'] == audit_id_a for r in hist_b_all.json()))

        # 5. Check officer analytics
        analytics_res = self.client.get('/api/analytics', headers=headers_a)
        self.assertEqual(analytics_res.status_code, 200)
        adata = analytics_res.json()
        self.assertEqual(adata['officer_name'], 'Officer Anita Desai')
        self.assertGreaterEqual(adata['officer_audit_count'], 1)

    def test_rbac_inspector_role_and_role_assignment(self):
        import uuid
        uid = uuid.uuid4().hex[:6]
        # 1. Login Inspector (Admin / Senior Officer)
        res_insp = self.client.post('/api/auth/demo-login', json={
            'name': f'Chief Inspector {uid}',
            'email': f'arjun_{uid}@legalmetrology.gov.in',
            'role': 'Senior Legal Metrology Officer'
        })
        insp_token = res_insp.json()['token']
        insp_headers = {'Authorization': f'Bearer {insp_token}'}

        # 2. Login standard Field Officer (Non-inspector)
        res_field = self.client.post('/api/auth/demo-login', json={
            'name': f'Field Officer {uid}',
            'email': f'rakesh_{uid}@legalmetrology.gov.in',
            'role': 'Field Officer'
        })
        field_token = res_field.json()['token']
        field_user_id = res_field.json()['user']['id']
        field_headers = {'Authorization': f'Bearer {field_token}'}

        # 3. Field Officer is FORBIDDEN from accessing all department ledgers
        blocked_res = self.client.get('/api/history?scope=all', headers=field_headers)
        self.assertEqual(blocked_res.status_code, 403)
        self.assertIn("Only authorized Legal Metrology Inspectors", blocked_res.json()['detail'])

        # 4. Field Officer is FORBIDDEN from assigning roles
        unauth_role_res = self.client.post(
            f'/api/users/{field_user_id}/role',
            json={'role': 'Legal Metrology Inspector'},
            headers=field_headers
        )
        self.assertEqual(unauth_role_res.status_code, 403)

        # 5. Inspector lists users and promotes Field Officer to Inspector
        users_res = self.client.get('/api/users', headers=insp_headers)
        self.assertEqual(users_res.status_code, 200)
        self.assertTrue(any(u['id'] == field_user_id for u in users_res.json()['users']))

        promote_res = self.client.post(
            f'/api/users/{field_user_id}/role',
            json={'role': 'Legal Metrology Inspector'},
            headers=insp_headers
        )
        self.assertEqual(promote_res.status_code, 200)
        self.assertEqual(promote_res.json()['user']['role'], 'Legal Metrology Inspector')

        # 6. Promoted Officer can now access all department ledgers
        allowed_res = self.client.get('/api/history?scope=all', headers=field_headers)
        self.assertEqual(allowed_res.status_code, 200)
        self.assertIsInstance(allowed_res.json(), list)

    def test_google_auth_invalid_token(self):
        res = self.client.post('/api/auth/google', json={'credential': 'invalid_fake_token_12345'})
        self.assertEqual(res.status_code, 401)
        self.assertIn('Invalid or expired Google credential', res.json()['detail'])

if __name__ == '__main__':
    unittest.main()
