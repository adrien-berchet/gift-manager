"""Tests for the public Help pages."""

import pytest
from django.urls import reverse

from gift_manager.help_topics import CORE_SECTION_IDS
from gift_manager.help_topics import HELP_TOPICS
from gift_manager.help_topics import get_help_topic


@pytest.mark.django_db
class TestHelpPages:
    """The Help index and topic pages."""

    def test_index_is_public_and_lists_every_topic(self, client):
        """Logged-out visitors see the index with a link to every topic."""
        response = client.get(reverse("gift_manager:help_index"))

        assert response.status_code == 200
        html = response.content.decode()
        for topic in HELP_TOPICS:
            assert reverse("gift_manager:help_topic", args=[topic.slug]) in html

    @pytest.mark.parametrize("slug", [topic.slug for topic in HELP_TOPICS])
    def test_every_topic_renders_logged_out(self, client, slug):
        """Every topic page is public and shows its title."""
        response = client.get(reverse("gift_manager:help_topic", args=[slug]))

        assert response.status_code == 200
        assert str(get_help_topic(slug).title) in response.content.decode()

    def test_topic_renders_logged_in(self, authenticated_client):
        """A signed-in user can read a topic too."""
        response = authenticated_client.get(
            reverse("gift_manager:help_topic", args=["how-it-works"])
        )

        assert response.status_code == 200

    @pytest.mark.parametrize("slug", ["nope", "base", "topics", "topic", "index"])
    def test_unknown_topic_is_404(self, client, slug):
        """Only registered slugs render; template names are never built from the URL."""
        response = client.get(reverse("gift_manager:help_topic", args=[slug]))

        assert response.status_code == 404

    def test_dotted_path_is_404(self, client):
        """A path that tries to climb out of the topic folder does not render a template."""
        response = client.get("/help/../base/")

        assert response.status_code == 404

    def test_core_page_has_every_section_anchor(self, client):
        """The core page has one anchor per concept for the checklist links."""
        html = client.get(
            reverse("gift_manager:help_topic", args=["how-it-works"])
        ).content.decode()

        for section_id in CORE_SECTION_IDS:
            assert f'id="{section_id}"' in html

    def test_navbar_has_help_link_for_everyone(self, client, authenticated_client):
        """The navbar links to Help when logged out and logged in."""
        help_url = reverse("gift_manager:help_index")

        assert f'href="{help_url}"' in client.get(reverse("gift_manager:home")).content.decode()
        assert (
            f'href="{help_url}"'
            in authenticated_client.get(reverse("gift_manager:home")).content.decode()
        )

    def test_welcome_page_links_to_core_topic(self, client):
        """The logged-out welcome page links to the core Help page."""
        html = client.get(reverse("gift_manager:home")).content.decode()

        assert reverse("gift_manager:help_topic", args=["how-it-works"]) in html

    def test_get_help_topic_returns_none_for_unknown_slug(self):
        """The registry lookup gives None for a slug it does not know."""
        assert get_help_topic("nope") is None
        assert get_help_topic("wishlist").slug == "wishlist"
