"""Tests for admin topic notes routes."""


class TestTopicNotesList:
    """Test topic notes list view."""

    def test_requires_auth(self, client):
        """Unauthenticated requests redirect to login."""
        resp = client.get("/admin/topic-notes")
        assert resp.status_code == 302
        assert "/admin/login" in resp.location

    def test_list_renders(self, auth_client):
        """Authenticated user can see topic notes page."""
        resp = auth_client.get("/admin/topic-notes")
        assert resp.status_code == 200


class TestTopicNotesCRUD:
    """Test topic notes CRUD operations."""

    def test_create_note_redirects(self, app, auth_client):
        """Creating note redirects to list page."""
        with app.app_context():
            resp = auth_client.post(
                "/admin/topic-notes/create",
                data={
                    "topic": "AI Safety",
                    "note": "Important context about AI safety research.",
                    "source": "research",
                },
                follow_redirects=False,
            )
            assert resp.status_code == 302
            assert "/admin/topic-notes" in resp.location

    def test_create_note_requires_topic(self, app, auth_client):
        """Creating note without topic shows error and redirects."""
        with app.app_context():
            resp = auth_client.post(
                "/admin/topic-notes/create",
                data={"topic": "", "note": "Some note"},
                follow_redirects=False,
            )
            assert resp.status_code == 302

    def test_create_and_list_note(self, app, auth_client):
        """Can create a note and see it in the list."""
        with app.app_context():
            auth_client.post(
                "/admin/topic-notes/create",
                data={"topic": "AI Safety", "note": "Test note", "source": ""},
            )
            resp = auth_client.get("/admin/topic-notes")
            assert resp.status_code == 200
            assert "AI Safety" in resp.text
            assert "Test note" in resp.text

    def test_delete_note(self, app, auth_client):
        """Can delete a note."""
        with app.app_context():
            auth_client.post(
                "/admin/topic-notes/create",
                data={"topic": "Delete Test", "note": "To be deleted", "source": ""},
            )
            resp = auth_client.post(
                "/admin/topic-notes/delete",
                data={"topic": "Delete Test", "source": ""},
                follow_redirects=False,
            )
            assert resp.status_code == 302
