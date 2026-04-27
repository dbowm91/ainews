"""Tests for admin share endpoints."""



class TestShares:
    def test_shares_requires_auth(self, client):
        resp = client.get("/admin/shares")
        assert resp.status_code in (302, 401)

    def test_shares_renders(self, auth_client, app):
        from extensions import db
        from models import ShareConfig

        with app.app_context():
            config = ShareConfig(
                platform_key="twitter",
                label="Twitter",
                url_template="https://twitter.com/intent/tweet?url={url}",
                icon_name="twitter",
                active=True,
                sort_order=1,
            )
            db.session.add(config)
            db.session.commit()

        resp = auth_client.get("/admin/shares")
        assert resp.status_code == 200

    def test_toggle_share_requires_auth(self, client, app):
        from extensions import db
        from models import ShareConfig

        with app.app_context():
            config = ShareConfig(
                platform_key="twitter",
                label="Twitter",
                url_template="https://twitter.com/intent/tweet?url={url}",
                icon_name="twitter",
                active=True,
                sort_order=1,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        resp = client.post(f"/admin/shares/{config_id}/toggle")
        assert resp.status_code in (302, 401)

    def test_toggle_share_active_to_inactive(self, auth_client, app):
        from extensions import db
        from models import ShareConfig

        with app.app_context():
            config = ShareConfig(
                platform_key="twitter2",
                label="Twitter",
                url_template="https://twitter.com/intent/tweet?url={url}",
                icon_name="twitter",
                active=True,
                sort_order=1,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        resp = auth_client.post(f"/admin/shares/{config_id}/toggle")
        assert resp.status_code in (200, 302)

        with app.app_context():
            db.session.expire_all()
            config = db.session.get(ShareConfig, config_id)
            assert config.active is False

    def test_toggle_share_inactive_to_active(self, auth_client, app):
        from extensions import db
        from models import ShareConfig

        with app.app_context():
            config = ShareConfig(
                platform_key="twitter3",
                label="Twitter",
                url_template="https://twitter.com/intent/tweet?url={url}",
                icon_name="twitter",
                active=False,
                sort_order=1,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        resp = auth_client.post(f"/admin/shares/{config_id}/toggle")
        assert resp.status_code in (200, 302)

        with app.app_context():
            db.session.expire_all()
            config = db.session.get(ShareConfig, config_id)
            assert config.active is True

    def test_toggle_share_404(self, auth_client):
        resp = auth_client.post("/admin/shares/99999/toggle")
        assert resp.status_code == 404
