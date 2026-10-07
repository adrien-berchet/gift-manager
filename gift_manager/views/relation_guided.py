"""Guided creation of a gift plan: recipient, gift and occasion in three steps."""

from django import forms
from django.db import transaction
from django.http import HttpResponse
from django.http import QueryDict
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy

from gift_manager.forms import RelationForm
from gift_manager.guided_plan import GUIDED_STEPS
from gift_manager.guided_plan import STEP_FORMS
from gift_manager.guided_plan import build_relation_data
from gift_manager.guided_plan import create_inline_objects

from .relation import RelationCreateView

STEP_LABELS = {
    "recipient": gettext_lazy("Recipient"),
    "gift": gettext_lazy("Gift"),
    "occasion": gettext_lazy("Event and gift plan"),
}


class RelationGuidedCreateView(RelationCreateView):
    """Create a gift plan through a short guided flow.

    One step is rendered per request. Answers of the other steps travel as hidden inputs, so no
    session state is needed and the flow works as plain multi-page forms without JavaScript. The
    final submit re-validates every step, then validates the plan with ``RelationForm`` so the
    result matches a plan created with the full form.
    """

    template_name = "gift_manager/relation_guided.html"
    htmx_template_name = "gift_manager/includes/relation_guided_partial.html"
    form_type = "relation-guided"

    def get(self, request, *args, **kwargs):
        self.object = None
        step = self._parse_step(request.GET.get("step"))
        return self._render_step(step, self._initial_form(step, {}))

    def post(self, request, *args, **kwargs):
        self.object = None
        step = self._parse_step(request.POST.get("step"))
        if request.POST.get("nav") == "back":
            target = max(step - 1, 1)
            return self._render_step(target, self._initial_form(target, request.POST))
        if step < len(GUIDED_STEPS):
            form = self._step_form(step, request.POST)
            if not form.is_valid():
                return self._render_step(step, form)
            return self._render_step(step + 1, self._initial_form(step + 1, request.POST))
        return self._finish()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_action_url"] = reverse("gift_manager:relation_guided_create")
        context["full_form_url"] = reverse("gift_manager:relation_create")
        context["translated_type"] = gettext("Gift Plan")
        return context

    @staticmethod
    def _parse_step(value) -> int:
        """Return a step number clamped to the known steps (1 for anything unusable)."""
        try:
            return min(max(int(value), 1), len(GUIDED_STEPS))
        except (TypeError, ValueError):
            return 1

    def _step_form(self, step: int, data=None, *, initial_values=None) -> forms.Form:
        name = GUIDED_STEPS[step - 1]
        kwargs = {}
        if name == "occasion":
            # The plan's surprise default depends on the recipient chosen in step 1
            posted = self._posted()
            new_person = posted.get("recipient_mode") == "new"
            kwargs["recipient_value"] = "" if new_person else posted.get("recipient", "")
        return STEP_FORMS[name](
            data, user=self.request.user, initial_values=initial_values, **kwargs
        )

    def _posted(self) -> QueryDict:
        return self.request.POST if self.request.method == "POST" else QueryDict()

    def _initial_form(self, step: int, data) -> forms.Form:
        """Return an unbound form of ``step`` showing the values already entered in ``data``."""
        return self._step_form(step, initial_values=data)

    def _render_step(self, step: int, form: forms.Form) -> HttpResponse:
        """Render ``step`` with ``form``; the other steps' answers become hidden inputs."""
        data = self._posted()
        carried = [
            (name, value)
            for other in range(1, len(GUIDED_STEPS) + 1)
            if other != step
            for name in self._step_form(other).input_names()
            for value in data.getlist(name)
        ]
        context = self.get_context_data(
            form=form,
            step=step,
            step_form=form,
            steps=[
                {
                    "number": number,
                    "label": STEP_LABELS[name],
                    "state": "current" if number == step else "done" if number < step else "todo",
                }
                for number, name in enumerate(GUIDED_STEPS, start=1)
            ],
            is_last_step=step == len(GUIDED_STEPS),
            carried=carried,
        )
        return self.render_to_response(context)

    def _finish(self) -> HttpResponse:
        """Create the plan (and inline gift/event) from the answers of all three steps."""
        user = self.request.user
        step_forms = {
            name: self._step_form(number, self.request.POST)
            for number, name in enumerate(GUIDED_STEPS, start=1)
        }
        for number, name in enumerate(GUIDED_STEPS, start=1):
            if not step_forms[name].is_valid():
                return self._render_step(number, step_forms[name])

        occasion_form = step_forms["occasion"]
        messages: list[str] = []
        try:
            with transaction.atomic():
                inline = create_inline_objects(
                    user, step_forms["recipient"], step_forms["gift"], occasion_form
                )
                plan_form = RelationForm(
                    build_relation_data(user, inline, occasion_form), user=user
                )
                if plan_form.is_valid():
                    return self.form_valid(plan_form)
                messages = [message for errors in plan_form.errors.values() for message in errors]
                # Undo the inline gift and event: the plan they were created for is rejected
                transaction.set_rollback(True)
        except forms.ValidationError as exc:
            messages = exc.messages
        for message in messages or [gettext("The gift plan could not be created.")]:
            occasion_form.add_error(None, message)
        return self._render_step(len(GUIDED_STEPS), occasion_form)
