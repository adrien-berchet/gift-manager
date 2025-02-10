# filepath: /home/adrien/Work/Perso/GiftManager/gift_manager/views.py
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.mail import send_mail
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext
from django.views.generic import DeleteView
from django.views.generic import DetailView
from django.views.generic import ListView
from django.views.generic import UpdateView
from django.views.generic.edit import CreateView

from .forms import EventForm
from .forms import GiftForm
from .forms import GiftRelationForm
from .forms import PersonForm
from .forms import PersonGroupAddMultiplePersonsForm
from .forms import PersonGroupForm
from .forms import PersonGroupRelationForm
from .forms import PersonRelationForm
from .models import Event
from .models import Gift
from .models import Invitation
from .models import Person
from .models import PersonGroup
from .models import Profile
from .models import Relation
from .models import RelationStatus


def home(request):
    """Home page view."""
    return render(request, "gift_manager/home.html")


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = Profile
    template_name = "gift_manager/profile_detail.html"
    context_object_name = "profile"

    def get_object(self):
        return Profile.objects.get(user=self.request.user)


def send_invitation(request):
    if request.method == "POST":
        recipient_email = request.POST.get("recipient_email")
        invitation = Invitation.objects.create(sender=request.user, recipient_email=recipient_email)
        invitation_link = request.build_absolute_uri(
            reverse("gift_manager:accept_invitation", args=[invitation.token])
        )
        send_mail(
            subject=gettext("Join my friends on Gift Manager"),
            message=(
                f"{gettext('To accept the invitation, click on the following link:')} "
                f"{invitation_link}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
        )
        return redirect("gift_manager:profile_detail")
    return render(request, "gift_manager/send_invitation.html")


def accept_invitation(request, token):
    invitation = get_object_or_404(Invitation, token=token, accepted=False)
    # If the user is already logged in, establish the friendship relationship
    if request.user.is_authenticated:
        invitation.accepted = True
        invitation.accepted_at = timezone.now()
        invitation.save()
        # Create or get the user's profile
        user_profile, _ = Profile.objects.get_or_create(user=request.user)
        sender_profile, _ = Profile.objects.get_or_create(user=invitation.sender)
        # Add the sender to the user's friends and vice versa
        user_profile.friends.add(sender_profile)
        sender_profile.friends.add(user_profile)
        user_profile.save()
        sender_profile.save()
        return redirect("gift_manager:profile_detail")
    # Otherwise, redirect to the registration with the token
    # (to be handled in the registration process)
    return redirect(f"{reverse('account_signup')}?invitation_token={token}")


@login_required
def remove_friend(request, friend_id):
    if request.method == "POST":
        friend_profile = get_object_or_404(Profile, pk=friend_id)
        user_profile = get_object_or_404(Profile, user=request.user)
        # Remove the friend relationship (symmetric)
        if friend_profile in user_profile.friends.all():
            user_profile.friends.remove(friend_profile)

        # Remove all shared objects between the two users
        persons_shared = Person.objects.filter(shared_with=request.user)
        for person in persons_shared:
            if friend_profile.user in person.shared_with.all():
                person.shared_with.remove(friend_profile.user)
    return redirect("gift_manager:profile_detail")


class FilterByUserMixin:
    """Mixin to filter objects by the current user."""

    def get_queryset(self):
        return self.model.objects.filter(Q(shared_with=self.request.user))


class GetObjectByTokenMixin:
    """Mixin to get an object by its token."""

    pk_name = None

    def get_object(self, queryset=None):
        queryset = self.get_queryset()
        obj_id = self.kwargs.get("pk")
        if obj_id is None:
            msg = "No object found matching the query"
            raise Http404(msg)
        if self.pk_name is None:
            msg = "pk_name attribute is required"
            raise AttributeError(msg)
        kwargs = {self.pk_name: obj_id}
        return get_object_or_404(queryset, **kwargs)


class PersonListView(LoginRequiredMixin, ListView):
    model = Person
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    column_names = {
        "first_name": "First Name",
        "family_name": "Family Name",
        "email_address": "Email Address",
        "groups": "Groups",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Persons"
        context["translated_type"] = gettext("Persons")
        context["column_names"] = self.column_names

        return context

    def get_queryset(self):
        """Return Persons for the current user or shared with the user."""
        queryset = (
            Person.objects.filter(Q(shared_with=self.request.user))
            .values("person_id", *list(set(self.column_names.keys()).difference(["groups"])))
            .annotate(
                group_names=Coalesce(
                    ArrayAgg("groups__name", distinct=True),  # Retrieve the list of group names
                    [],
                ),
                group_ids=Coalesce(
                    ArrayAgg("groups__group_id", distinct=True),  # Retrieve the list of group UUIDs
                    [],
                ),
            )
        )

        # Transform the list of group names and UUIDs into a list of tuples
        for person in queryset:
            person["grouped_groups"] = [
                (i, j)
                for i, j in list(zip(person["group_names"], person["group_ids"]))
                if i is not None and j is not None
            ]

        return queryset


class PersonCreateView(LoginRequiredMixin, CreateView):
    model = Person
    form_class = PersonForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    success_url = reverse_lazy("gift_manager:persons")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Person"
        context["translated_type"] = gettext("Person")
        context["action"] = gettext("Create")
        context["cancel_url"] = reverse_lazy("gift_manager:persons")
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["shared_with"].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Add current user
        if form.cleaned_data["shared_with"]:
            form.instance.shared_with.add(*form.cleaned_data["shared_with"])
        return response


class PersonUpdateView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, UpdateView):
    model = Person
    form_class = PersonForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    pk_name = "person_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Person"
        context["translated_type"] = gettext("Person")
        context["action"] = gettext("Edit")
        context["cancel_url"] = reverse_lazy(
            "gift_manager:person_detail", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["shared_with"].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Add current user
        if form.cleaned_data["shared_with"]:
            form.instance.shared_with.add(*form.cleaned_data["shared_with"])
        return response

    def get_success_url(self):
        return reverse("gift_manager:person_detail", kwargs={"pk": self.object.person_id})


class PersonDeleteView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteView):
    model = Person
    template_name = "gift_manager/confirm_delete.html"
    success_url = reverse_lazy("gift_manager:persons")
    pk_name = "person_id"


class PersonGroupListView(LoginRequiredMixin, ListView):
    model = PersonGroup
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    column_names = {
        "name": "Group Name",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Groups"
        context["translated_type"] = gettext("Groups")
        context["column_names"] = self.column_names
        return context

    def get_queryset(self):
        return PersonGroup.objects.filter(Q(shared_with=self.request.user)).values(
            "group_id", *self.column_names
        )


class PersonGroupCreateView(LoginRequiredMixin, CreateView):
    model = PersonGroup
    form_class = PersonGroupForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    success_url = reverse_lazy("gift_manager:person_groups")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Person group"
        context["translated_type"] = gettext("Person group")
        context["action"] = gettext("Create")
        context["cancel_url"] = reverse_lazy("gift_manager:person_groups")
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["shared_with"].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Add current user
        if form.cleaned_data["shared_with"]:
            form.instance.shared_with.add(*form.cleaned_data["shared_with"])
        return response


class PersonGroupUpdateView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, UpdateView
):
    model = PersonGroup
    form_class = PersonGroupForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    pk_name = "group_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Person group"
        context["translated_type"] = gettext("Person group")
        context["action"] = gettext("Edit")
        context["cancel_url"] = reverse_lazy(
            "gift_manager:person_group_detail", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["shared_with"].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Add current user
        if form.cleaned_data["shared_with"]:
            form.instance.shared_with.add(*form.cleaned_data["shared_with"])
        return response

    def get_success_url(self):
        return reverse("gift_manager:person_group_detail", kwargs={"pk": self.object.group_id})


def add_multiple_persons_to_group(request, pk):
    group = get_object_or_404(PersonGroup, group_id=pk)
    if request.method == "POST":
        form = PersonGroupAddMultiplePersonsForm(request.POST, user=request.user)
        if form.is_valid():
            form.save(group)
            return redirect("gift_manager:person_group_detail", pk=pk)
    else:
        form = PersonGroupAddMultiplePersonsForm(user=request.user)

    return render(
        request,
        "gift_manager/person_group_add_person_form.html",
        {
            "group": group,
            "form": form,
        },
    )


def remove_person_from_group(request, pk, person_id):  # noqa: ARG001
    group = get_object_or_404(PersonGroup, group_id=pk)
    person = get_object_or_404(Person, person_id=person_id)
    person.groups.remove(group)
    return redirect("gift_manager:person_group_detail", pk=pk)


class PersonGroupDeleteView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteView
):
    model = PersonGroup
    template_name = "gift_manager/confirm_delete.html"
    success_url = reverse_lazy("gift_manager:person_groups")
    pk_name = "persongroup_id"


class GiftListView(LoginRequiredMixin, ListView):
    model = Gift
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    column_names = {
        "name": "Gift Name",
        "comment": "Comment",
        "tags": "Tags",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Gifts"
        context["translated_type"] = gettext("Gifts")
        context["column_names"] = self.column_names
        return context

    def get_queryset(self):
        """Return Gifts for the current user or shared with the user."""
        return Gift.objects.filter(Q(shared_with=self.request.user)).values(
            "gift_id", *self.column_names
        )


class GiftCreateView(LoginRequiredMixin, CreateView):
    model = Gift
    form_class = GiftForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    success_url = reverse_lazy("gift_manager:gifts")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Gift"
        context["translated_type"] = gettext("Gift")
        context["action"] = gettext("Create")
        context["cancel_url"] = reverse_lazy("gift_manager:gifts")
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["shared_with"].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields["shared_with"].required = False  # Make the field optional in the form
        form.fields["tags"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Add current user
        if form.cleaned_data["shared_with"]:
            form.instance.shared_with.add(*form.cleaned_data["shared_with"])
        return response


class GiftUpdateView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, UpdateView):
    model = Gift
    template_name = "gift_manager/create_form.html"
    fields = ["name", "comment", "tags"]
    login_url = "/accounts/login/"
    pk_name = "gift_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Gift"
        context["translated_type"] = gettext("Gift")
        context["action"] = gettext("Edit")
        context["cancel_url"] = reverse_lazy(
            "gift_manager:gift_detail", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["shared_with"].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields["shared_with"].required = False  # Make the field optional in the form
        form.fields["tags"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Add current user
        if form.cleaned_data["shared_with"]:
            form.instance.shared_with.add(*form.cleaned_data["shared_with"])
        return response

    def get_success_url(self):
        return reverse("gift_manager:gift_detail", kwargs={"pk": self.object.person_id})


class GiftDeleteView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteView):
    model = Gift
    template_name = "gift_manager/confirm_delete.html"
    success_url = reverse_lazy("gift_manager:gifts")
    pk_name = "gift_id"


class EventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    column_names = {
        "name": "Event Name",
        "comment": "Comment",
        "usual_date": "Usual date",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Events"
        context["translated_type"] = gettext("Events")
        context["column_names"] = self.column_names
        return context

    def get_queryset(self):
        """Return Events for the current user or shared with the user."""
        return Event.objects.filter(Q(shared_with=self.request.user)).values(
            "event_id", *self.column_names
        )


class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    success_url = reverse_lazy("gift_manager:events")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Event"
        context["translated_type"] = gettext("Event")
        context["action"] = gettext("Create")
        context["cancel_url"] = reverse_lazy("gift_manager:events")
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["shared_with"].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Add current user
        if form.cleaned_data["shared_with"]:
            form.instance.shared_with.add(*form.cleaned_data["shared_with"])
        return response


class EventUpdateView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, UpdateView):
    model = Event
    form_class = EventForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    success_url = reverse_lazy("gift_manager:events")
    pk_name = "event_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Event"
        context["translated_type"] = gettext("Event")
        context["action"] = gettext("Edit")
        context["cancel_url"] = reverse_lazy(
            "gift_manager:event_detail", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["shared_with"].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Add current user
        if form.cleaned_data["shared_with"]:
            form.instance.shared_with.add(*form.cleaned_data["shared_with"])
        return response

    def get_success_url(self):
        return reverse("gift_manager:event_detail", kwargs={"pk": self.object.person_id})


class EventDeleteView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteView):
    model = Event
    template_name = "gift_manager/confirm_delete.html"
    success_url = reverse_lazy("gift_manager:events")
    pk_name = "event_id"


class PersonDetailView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DetailView):
    model = Person
    template_name = "gift_manager/person_detail.html"
    context_object_name = "person"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "person_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(
            Q(person=self.object) | Q(group__in=self.object.groups.all())
        )
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class PersonGroupDetailView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DetailView
):
    model = PersonGroup
    template_name = "gift_manager/person_group_detail.html"
    context_object_name = "group"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "group_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["persons"] = Person.objects.filter(groups=self.object)
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class GiftDetailView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DetailView):
    model = Gift
    template_name = "gift_manager/gift_detail.html"
    context_object_name = "gift"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "gift_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(gift=self.object)
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class EventDetailView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DetailView):
    model = Event
    template_name = "gift_manager/event_detail.html"
    context_object_name = "event"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "event_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(event=self.object)
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class PersonRelationCreateView(LoginRequiredMixin, CreateView):
    model = Relation
    form_class = PersonRelationForm
    template_name = "gift_manager/create_person_relation_form.html"
    login_url = "/accounts/login/"

    def get_initial(self):
        initial = super().get_initial()
        initial["person"] = self.kwargs["pk"]
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["person"] = Person.objects.get(person_id=self.kwargs["pk"])
        return context

    def form_valid(self, form):
        form.instance.person = Person.objects.get(person_id=self.kwargs["pk"])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("gift_manager:person_detail", kwargs={"pk": self.kwargs["pk"]})


class PersonGroupRelationCreateView(LoginRequiredMixin, CreateView):
    model = Relation
    form_class = PersonGroupRelationForm
    template_name = "gift_manager/create_group_relation_form.html"
    login_url = "/accounts/login/"

    def get_initial(self):
        initial = super().get_initial()
        initial["group"] = self.kwargs["pk"]
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["group"] = PersonGroup.objects.get(group_id=self.kwargs["pk"])
        return context

    def form_valid(self, form):
        form.instance.group = PersonGroup.objects.get(group_id=self.kwargs["pk"])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("gift_manager:person_group_detail", kwargs={"pk": self.kwargs["pk"]})


class GiftRelationCreateView(LoginRequiredMixin, CreateView):
    model = Relation
    form_class = GiftRelationForm
    template_name = "gift_manager/create_gift_relation_form.html"
    login_url = "/accounts/login/"

    def get_initial(self):
        initial = super().get_initial()
        initial["gift"] = self.kwargs["pk"]
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["gift"] = Gift.objects.get(gift_id=self.kwargs["pk"])
        return context

    def form_valid(self, form):
        form.instance.gift = Gift.objects.get(gift_id=self.kwargs["pk"])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("gift_manager:gift_detail", kwargs={"pk": self.kwargs["pk"]})


class RelationStatusListView(LoginRequiredMixin, ListView):
    model = RelationStatus
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    column_names = {
        "status": "Status",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Status"
        context["translated_type"] = gettext("Status")
        context["column_names"] = self.column_names
        return context

    def get_queryset(self):
        """Return RelationStatus."""
        return RelationStatus.objects.values("pk", *self.column_names)


class RelationStatusDetailView(LoginRequiredMixin, DetailView):
    model = RelationStatus
    template_name = "gift_manager/relation_status_detail.html"
    context_object_name = "status"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(status=self.object)
        return context
