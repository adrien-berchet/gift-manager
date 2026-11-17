"""Public Help pages."""

from django.http import Http404
from django.views.generic import TemplateView

from gift_manager.help_topics import HELP_TOPICS
from gift_manager.help_topics import get_help_topic


class HelpIndexView(TemplateView):
    """List every Help topic. Public."""

    template_name = "gift_manager/help/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["topics"] = HELP_TOPICS
        context["getting_started_hidden"] = False
        return context


class HelpTopicView(TemplateView):
    """Render one registered Help topic. Public."""

    template_name = "gift_manager/help/topic.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        topic = get_help_topic(kwargs["topic"])
        if topic is None:
            raise Http404
        context["topic"] = topic
        context["topics"] = HELP_TOPICS
        return context
