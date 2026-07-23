import io
import unittest
from unittest.mock import patch

from app import create_app
from app.models import BanList, BanListCard, BanListCardChange


def fake_card(cid):
    return {
        "id": int(cid),
        "name": f"测试卡片 {cid}",
        "type": 1,
    }


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.catalog_patch = patch(
            "app.services.catalog.get_card",
            side_effect=fake_card,
        )
        self.catalog_patch.start()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "EDIT_PASSWORD": "test-password",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.catalog_patch.stop()

    def login(self):
        return self.client.post(
            "/edit/login",
            data={
                "password": "test-password",
                "year": "2026",
                "region": "0",
                "mode": "changes",
            },
            follow_redirects=True,
        )

    def create_ban_list(self):
        return self.client.post(
            "/edit/create",
            data={
                "year": "2026",
                "region": "0",
                "mode": "changes",
                "effective_date": "2026-04-01",
                "use_csv": "no",
            },
            follow_redirects=True,
        )

    def test_public_and_editor_pages_render(self):
        home = self.client.get("/")
        full = self.client.get("/?mode=full")
        editor = self.client.get("/manage")
        legacy_editor = self.client.get("/edit")

        self.assertEqual(home.status_code, 200)
        self.assertEqual(full.status_code, 200)
        self.assertEqual(editor.status_code, 200)
        self.assertEqual(legacy_editor.status_code, 200)
        self.assertNotIn("在线编辑", home.get_data(as_text=True))
        self.assertNotIn(
            "/static/css/editor.css",
            home.get_data(as_text=True),
        )
        self.assertIn(
            "/static/css/editor.css",
            editor.get_data(as_text=True),
        )

    def test_frontend_assets_are_available(self):
        for path in (
            "/static/style.css",
            "/static/css/base.css",
            "/static/css/components.css",
            "/static/css/editor.css",
            "/static/edit.js",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_editor_mutation_requires_authentication(self):
        response = self.create_ban_list()

        self.assertIn(
            "请先输入密码完成验证后再进行修改",
            response.get_data(as_text=True),
        )
        with self.app.app_context():
            self.assertEqual(BanList.query.count(), 0)

    def test_card_and_ban_list_lifecycle(self):
        self.assertEqual(self.login().status_code, 200)
        create_response = self.create_ban_list()
        self.assertIn("已创建 2026-04-01", create_response.get_data(as_text=True))

        add_response = self.client.post(
            "/edit",
            data={
                "operation": "add",
                "year": "2026",
                "region": "0",
                "effective_date": "2026-04-01",
                "cid": "1001",
                "old_status": "3",
                "new_status": "1",
                "notes": "首次限制",
            },
            follow_redirects=True,
        )
        self.assertIn("已新增 CID 1001", add_response.get_data(as_text=True))

        changes = self.client.get(
            "/?year=2026&region=0&mode=changes&effective_date=2026-04-01"
        )
        full = self.client.get(
            "/?year=2026&region=0&mode=full&effective_date=2026-04-01"
        )
        self.assertIn("测试卡片 1001", changes.get_data(as_text=True))
        self.assertIn("测试卡片 1001", full.get_data(as_text=True))

        with self.app.app_context():
            card = BanListCard.query.filter_by(cid=1001).one()
            card_id = card.id

        update_response = self.client.post(
            "/edit",
            data={
                "operation": "update",
                "year": "2026",
                "region": "0",
                "effective_date": "2026-04-01",
                "card_id": str(card_id),
                "old_status": "1",
                "new_status": "0",
                "notes": "改为禁止",
            },
            follow_redirects=True,
        )
        self.assertIn("已更新 CID 1001", update_response.get_data(as_text=True))

        date_response = self.client.post(
            "/edit/change-date",
            data={
                "year": "2026",
                "region": "0",
                "mode": "changes",
                "effective_date": "2026-04-01",
                "new_effective_date": "2026-05-01",
            },
            follow_redirects=True,
        )
        self.assertIn("修改为 2026-05-01", date_response.get_data(as_text=True))

        delete_response = self.client.post(
            "/edit/delete",
            data={
                "year": "2026",
                "region": "0",
                "mode": "changes",
                "effective_date": "2026-05-01",
                "confirm_delete": "yes",
            },
            follow_redirects=True,
        )
        self.assertIn("已删除 2026-05-01", delete_response.get_data(as_text=True))

        with self.app.app_context():
            self.assertEqual(BanList.query.count(), 0)
            self.assertEqual(BanListCard.query.count(), 0)
            self.assertEqual(BanListCardChange.query.count(), 0)

    def test_csv_append_and_overwrite(self):
        self.login()
        self.create_ban_list()

        append_response = self.client.post(
            "/upload",
            data={
                "year": "2026",
                "region": "0",
                "effective_date": "2026-04-01",
                "upload_mode": "append",
                "banlist_csv": (
                    io.BytesIO(b"1001,3,1\n1002,3,2\n"),
                    "banlist.csv",
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("新增 2，更新 0", append_response.get_data(as_text=True))

        overwrite_response = self.client.post(
            "/upload",
            data={
                "year": "2026",
                "region": "0",
                "effective_date": "2026-04-01",
                "upload_mode": "overwrite",
                "confirm_overwrite": "yes",
                "banlist_csv": (
                    io.BytesIO(b"2001,3,0\n"),
                    "banlist.csv",
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("新增 1，更新 0", overwrite_response.get_data(as_text=True))

        with self.app.app_context():
            cards = BanListCard.query.all()
            self.assertEqual([card.cid for card in cards], [2001])
            self.assertEqual(BanListCardChange.query.count(), 1)

    def test_invalid_query_parameters_redirect_to_defaults(self):
        response = self.client.get("/?region=invalid")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")


if __name__ == "__main__":
    unittest.main()
