from collections.abc import Sequence
from typing import TypeAlias
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.mail import send_mail
from django.db.models import Model
from django.db.models import Q
from django.db.models import TextField
from django.db.models import Value
from django.db.models.functions import Coalesce
from django.db.models.functions import Concat
from django.db.models.functions import NullIf
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.http import require_POST
from django.views.generic import DeleteView
from django.views.generic import DetailView
from django.views.generic import ListView
from django.views.generic import UpdateView
from django.views.generic import View
from django.views.generic.edit import CreateView

from .forms import EventForm
from .forms import GiftForm
from .forms import GiftRelationForm
from .forms import PersonForm
from .forms import PersonGroupAddMultiplePersonsForm
from .forms import PersonGroupForm
from .forms import PersonGroupRelationForm
from .forms import PersonRelationForm
from .forms import RelationForm
from .models import Event
from .models import EventPermission
from .models import Gift
from .models import GiftPermission
from .models import Invitation
from .models import Person
from .models import PersonGroup
from .models import PersonGroupPermission
from .models import PersonPermission
from .models import Profile
from .models import Relation
from .models import RelationPermission
from .models import RelationStatus

# Type definitions for clarity
ModelType: TypeAlias = type[Model]
SharedObjectType = Person | PersonGroup | Gift | Event | Relation


def home(request):
    """Home page view."""
    return render(request, "gift_manager/home.html")


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = Profile
    template_name = "gift_manager/profile_detail.html"
    context_object_name = "profile"

    def get_object(self):
        return Profile.objects.get(user=self.request.user)


class SendInvitationView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return render(request, "gift_manager/send_invitation.html")

    def post(self, request, *args, **kwargs):
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


class AcceptInvitationView(View):
    def get(self, request, *args, **kwargs):
        token = self.kwargs.get("token")
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
            messages.success(
                request, gettext("You are now friend with {}").format(invitation.sender.username)
            )
            return redirect("gift_manager:profile_detail")
        # Otherwise, redirect to the registration with the token
        # (to be handled in the registration process)
        return redirect(f"{reverse('account_signup')}?invitation_token={token}")


class RemoveFriendView(LoginRequiredMixin, View):
    def post(self, request, friend_id, *args, **kwargs):
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

    def get(self, *args, **kwargs):
        # Redirect to the profile detail page
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


def get_permission(obj, user, filter_name):
    """Get the permission type for the user on the object."""
    permission = obj.shared_with.through.objects.filter(**{"user": user, filter_name: obj}).first()
    return permission.permission_type if permission else "viewer"


class ContextPermissionMixin:
    """Mixin to add permission context to the view."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["user_permission"] = get_permission(
            self.object, self.request.user, self.context_object_name
        )
        return context


class DeleteSharedMixin:
    """Mixin to delete shared objects."""

    def post(self, request, *args, **kwargs):
        """Overload the delete method to handle conditional deletion.

        If the person is shared with other users, only the sharing with the current user is removed.
        Otherwise, the person is completely deleted.
        """
        self.object = self.get_object()
        success_url = self.get_success_url()

        # Check if the person is shared with other users
        other_users = self.object.shared_with.exclude(id=request.user.id)

        if other_users.exists():
            # If shared, only remove the sharing with the current user
            self.object.shared_with.remove(request.user)

            # Delete the corresponding permission as well
            self.object.shared_with.through.objects.filter(
                user=request.user, person=self.object
            ).delete()

            messages.success(
                request,
                gettext(
                    "You no longer have access to this person, but it remains shared with other "
                    "users"
                ),
            )
        else:
            # If not shared, completely delete the object
            self.object.delete()
            messages.success(request, gettext("Person successfully deleted"))

        return redirect(success_url)


def handle_permissions(
    cls,
    current_user,
    related_object,
    viewer_users,
    object_attr,
    current_shared_users=None,
):
    # Add current user
    permission, created = cls.objects.get_or_create(
        user=current_user, **{object_attr: related_object}, defaults={"permission_type": "editor"}
    )
    if not created and not permission.permission_type:
        permission.permission_type = "editor"
        permission.save()

    # Add shared users
    for user in viewer_users:
        kwargs = {
            object_attr: related_object,
            "user": user,
            "defaults": {"permission_type": "viewer"},
        }
        permission, created = cls.objects.get_or_create(**kwargs)
        if not created and not permission.permission_type:
            permission.permission_type = "viewer"
            permission.save()

    if current_shared_users is not None:
        # Remove permissions for unselected users
        # (users who were previously shared but not in the current selection)
        users_to_remove = current_shared_users.exclude(id__in=[user.id for user in viewer_users])
        users_to_remove = users_to_remove.exclude(id=current_user.id)  # Don't remove current user

        for user in users_to_remove:
            # Remove the permission record
            cls.objects.filter(user=user, **{object_attr: related_object}).delete()


class PersonListView(LoginRequiredMixin, ListView):
    model = Person
    template_name = "gift_manager/person_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "first_name": gettext("First name"),
            "family_name": gettext("Family name"),
            "email_address": gettext("Email address"),
            "groups": gettext("Groups"),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "Persons"
        context["translated_type"] = gettext("Persons")
        context["column_names"] = self.column_names
        context["unique_groups"] = (
            PersonGroup.objects.filter(shared_with=self.request.user)
            .values("name")
            .distinct()
            .order_by("name")
        )

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
        form.fields["groups"].queryset = PersonGroup.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            PersonPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "person",
        )
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
        form.fields["groups"].queryset = PersonGroup.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        ).order_by("username")
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            PersonPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "person",
            current_shared_users=form.instance.shared_with.all(),
        )
        return response

    def get_success_url(self):
        return reverse("gift_manager:person_detail", kwargs={"pk": self.object.person_id})


class PersonDeleteView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteSharedMixin, DeleteView
):
    model = Person
    template_name = "gift_manager/confirm_delete.html"
    success_url = reverse_lazy("gift_manager:persons")
    pk_name = "person_id"


class PersonGroupListView(LoginRequiredMixin, ListView):
    model = PersonGroup
    template_name = "gift_manager/person_group_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Group name"),
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
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            PersonGroupPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "group",
        )
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
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            PersonGroupPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "group",
            current_shared_users=form.instance.shared_with.all(),
        )
        return response

    def get_success_url(self):
        return reverse("gift_manager:person_group_detail", kwargs={"pk": self.object.group_id})


def add_multiple_persons_to_group(request, pk):
    group = get_object_or_404(PersonGroup, group_id=pk)
    if request.method == "POST":
        form = PersonGroupAddMultiplePersonsForm(request.POST, user=request.user, group=group)
        if form.is_valid():
            form.save(group)
            return redirect("gift_manager:person_group_detail", pk=pk)
    else:
        form = PersonGroupAddMultiplePersonsForm(user=request.user, group=group)

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
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteSharedMixin, DeleteView
):
    model = PersonGroup
    template_name = "gift_manager/confirm_delete.html"
    success_url = reverse_lazy("gift_manager:person_groups")
    pk_name = "group_id"


class GiftListView(LoginRequiredMixin, ListView):
    model = Gift
    template_name = "gift_manager/gift_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Gift name"),
            "comment": gettext("Comment"),
            "tags": gettext("Tags"),
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
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        form.fields["tags"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            GiftPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "gift",
        )
        return response


class GiftUpdateView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, UpdateView):
    model = Gift
    template_name = "gift_manager/create_form.html"
    fields = ["name", "comment", "tags", "shared_with"]
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
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        form.fields["tags"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            GiftPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "gift",
            current_shared_users=form.instance.shared_with.all(),
        )
        return response

    def get_success_url(self):
        return reverse("gift_manager:gift_detail", kwargs={"pk": self.object.gift_id})


class GiftDeleteView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteSharedMixin, DeleteView
):
    model = Gift
    template_name = "gift_manager/confirm_delete.html"
    success_url = reverse_lazy("gift_manager:gifts")
    pk_name = "gift_id"


class EventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = "gift_manager/event_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "name": gettext("Event name"),
            "comment": gettext("Comment"),
            "usual_date": gettext("Usual date"),
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
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            PersonPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "event",
        )
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
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            EventPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "event",
            current_shared_users=form.instance.shared_with.all(),
        )
        return response

    def get_success_url(self):
        return reverse("gift_manager:event_detail", kwargs={"pk": self.object.person_id})


class EventDeleteView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteSharedMixin, DeleteView
):
    model = Event
    template_name = "gift_manager/confirm_delete.html"
    success_url = reverse_lazy("gift_manager:events")
    pk_name = "event_id"


class PersonDetailView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, ContextPermissionMixin, DetailView
):
    model = Person
    template_name = "gift_manager/person_detail.html"
    context_object_name = "person"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "person_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(
            (Q(person=self.object) | Q(group__in=self.object.groups.all()))
            & Q(shared_with=self.request.user)
        ).select_related("status")
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        context["relation_statuses"] = RelationStatus.objects.all()
        return context


class PersonGroupDetailView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, ContextPermissionMixin, DetailView
):
    model = PersonGroup
    template_name = "gift_manager/person_group_detail.html"
    context_object_name = "group"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "group_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["persons"] = Person.objects.filter(
            groups=self.object, shared_with=self.request.user
        )
        context["gifts"] = Relation.objects.filter(
            group=self.object, shared_with=self.request.user, gift__isnull=False
        )
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class GiftDetailView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, ContextPermissionMixin, DetailView
):
    model = Gift
    template_name = "gift_manager/gift_detail.html"
    context_object_name = "gift"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "gift_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(
            gift=self.object, shared_with=self.request.user
        )
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class EventDetailView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, ContextPermissionMixin, DetailView
):
    model = Event
    template_name = "gift_manager/event_detail.html"
    context_object_name = "event"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "event_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["relations"] = Relation.objects.filter(
            event=self.object, shared_with=self.request.user
        ).select_related("person", "group", "gift", "event", "status")
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

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.filter(shared_with=self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.person = Person.objects.get(person_id=self.kwargs["pk"])
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            RelationPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "relation",
        )
        return response

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

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["gift"].queryset = Gift.objects.filter(shared_with=self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.group = PersonGroup.objects.get(group_id=self.kwargs["pk"])
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            RelationPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "relation",
        )
        return response

    def get_success_url(self):
        url = reverse("gift_manager:person_group_detail", kwargs={"pk": self.object.group.group_id})
        query = urlencode({"tab": "gifts"})
        return f"{url}?{query}"


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

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["person"].queryset = (
            Person.objects.filter(shared_with=self.request.user)
            .annotate(
                complete_name=Concat(
                    "family_name",
                    Value(" "),
                    "first_name",
                    output_field=TextField(),
                ),
            )
            .order_by("complete_name")
        )
        form.fields["group"].queryset = PersonGroup.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.gift = Gift.objects.get(gift_id=self.kwargs["pk"])
        form.instance.user = self.request.user
        response = super().form_valid(form)
        # Add current user
        RelationPermission.objects.get_or_create(
            user=self.request.user, relation=form.instance, defaults={"permission_type": "editor"}
        )
        # Add shared users
        for user in form.cleaned_data["shared_with"]:
            RelationPermission.objects.get_or_create(
                user=user, relation=form.instance, defaults={"permission_type": "viewer"}
            )
        handle_permissions(
            RelationPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "relation",
        )
        return response

    def get_success_url(self):
        return reverse("gift_manager:gift_detail", kwargs={"pk": self.kwargs["pk"]})


class GiftRelationDeleteView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteSharedMixin, DeleteView
):
    model = Relation
    template_name = "gift_manager/confirm_delete.html"
    pk_name = "relation_id"

    def get_success_url(self):
        url = reverse("gift_manager:person_group_detail", kwargs={"pk": self.object.group.group_id})
        query = urlencode({"tab": "gifts"})
        return f"{url}?{query}"


class RelationStatusListView(LoginRequiredMixin, ListView):
    model = RelationStatus
    template_name = "gift_manager/status_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "status": gettext("Status"),
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
        context["relations"] = Relation.objects.filter(
            Q(status=self.object) & Q(shared_with=self.request.user)
        )
        return context


class RelationListView(LoginRequiredMixin, ListView):
    model = Relation
    template_name = "gift_manager/relation_list.html"
    context_object_name = "data"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column_names = {
            "gift__name": gettext("Gift"),
            "comment": gettext("Comment"),
            "related_object": gettext("Offered to"),
            "event": gettext("Event"),
            "status__status": gettext("Status"),
            "due_date": gettext("Due date"),
        }

    def get_queryset(self):
        return (
            Relation.objects.filter(Q(shared_with=self.request.user))
            .annotate(
                related_object=Coalesce(
                    NullIf(
                        Concat(
                            "person__first_name",
                            Value(" "),
                            "person__family_name",
                            output_field=TextField(),
                        ),
                        Value(" "),
                    ),
                    "group__name",
                    output_field=TextField(),
                )
            )
            .values(
                "relation_id",
                "gift__name",
                "gift__gift_id",
                "comment",
                "related_object",
                "person__person_id",
                "group__group_id",
                "event__name",
                "event__event_id",
                "status",
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["type"] = "Giftings"
        context["translated_type"] = gettext("Giftings")
        context["column_names"] = self.column_names
        context["relation_statuses"] = RelationStatus.objects.all()
        return context


class RelationCreateView(LoginRequiredMixin, CreateView):
    model = Relation
    form_class = RelationForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    success_url = reverse_lazy("gift_manager:relations")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hide_person = self.request.GET.get("hide_person", "false") == "true"
        kwargs["hide_person"] = hide_person
        hide_group = self.request.GET.get("hide_group", "false") == "true"
        kwargs["hide_group"] = hide_group
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["person"].queryset = (
            Person.objects.filter(shared_with=self.request.user)
            .annotate(
                complete_name=Concat(
                    "family_name",
                    Value(" "),
                    "first_name",
                    output_field=TextField(),
                ),
            )
            .order_by("complete_name")
        )
        form.fields["gift"].queryset = Gift.objects.filter(shared_with=self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            RelationPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "relation",
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "gifting"
        context["translated_type"] = gettext("gifting")
        context["action"] = gettext("Create")
        context["cancel_url"] = reverse_lazy("gift_manager:relations")
        return context


class RelationDetailView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, ContextPermissionMixin, DetailView
):
    model = Relation
    template_name = "gift_manager/relation_detail.html"
    context_object_name = "relation"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "relation_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["shared_with"] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class RelationUpdateView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, UpdateView):
    model = Relation
    form_class = RelationForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    pk_name = "relation_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["type"] = "gifting"
        context["translated_type"] = gettext("gifting")
        context["action"] = gettext("Edit")
        context["cancel_url"] = reverse_lazy(
            "gift_manager:relation_detail", kwargs={"pk": self.kwargs["pk"]}
        )
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        hide_person = self.request.GET.get("hide_person", "false") == "true"
        kwargs["hide_person"] = hide_person
        hide_group = self.request.GET.get("hide_group", "false") == "true"
        kwargs["hide_group"] = hide_group
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["person"].queryset = (
            Person.objects.filter(shared_with=self.request.user)
            .annotate(
                complete_name=Concat(
                    "family_name",
                    Value(" "),
                    "first_name",
                    output_field=TextField(),
                ),
            )
            .order_by("complete_name")
        )
        form.fields["gift"].queryset = Gift.objects.filter(shared_with=self.request.user).order_by(
            "name"
        )
        form.fields["event"].queryset = Event.objects.filter(
            shared_with=self.request.user
        ).order_by("name")
        form.fields["shared_with"].queryset = User.objects.filter(
            pk__in=self.request.user.profile.friends.all().values_list("user_id", flat=True)
        )
        form.fields["shared_with"].required = False  # Make the field optional in the form
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        handle_permissions(
            RelationPermission,
            self.request.user,
            form.instance,
            form.cleaned_data["shared_with"],
            "relation",
            current_shared_users=form.instance.shared_with.all(),
        )
        return response

    def get_success_url(self):
        if self.object.person_id is not None:
            pk = self.object.person_id
            url = "person_detail"
        else:
            pk = self.object.group.group_id
            url = "person_group_detail"
        return reverse(f"gift_manager:{url}", kwargs={"pk": pk})


class RelationDeleteView(
    FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DeleteSharedMixin, DeleteView
):
    model = Relation
    template_name = "gift_manager/confirm_delete.html"
    success_url = reverse_lazy("gift_manager:relations")
    pk_name = "relation_id"


@login_required
@require_POST
def update_relation_status(request):
    relation_id = request.POST.get("relation_id")
    new_status = request.POST.get("new_status")
    try:
        relation = Relation.objects.get(Q(relation_id=relation_id) & Q(shared_with=request.user))
        relation.status_id = new_status
        relation.save()
        return JsonResponse({"success": True})
    except Relation.DoesNotExist:
        return JsonResponse({"error": gettext("Gifting not found")}, status=404)


class ShareObjectsView(LoginRequiredMixin, View):
    """View for sharing objects with friends."""

    template_name = "gift_manager/share_objects.html"

    def get(self, request):
        """Display the sharing form."""
        # Get user's friends
        friends = User.objects.filter(
            pk__in=request.user.profile.friends.all().values_list("user_id", flat=True)
        ).select_related("profile")

        # Get the user's objects for each type
        persons = (
            Person.objects.filter(shared_with=request.user)
            .annotate(
                complete_name=Concat(
                    "family_name",
                    Value(" "),
                    "first_name",
                    output_field=TextField(),
                ),
            )
            .prefetch_related("groups")
            .order_by("complete_name")
        )
        person_groups = (
            PersonGroup.objects.filter(shared_with=request.user)
            .prefetch_related("person_set")
            .order_by("name")
        )
        gifts = Gift.objects.filter(shared_with=request.user).order_by("name")
        events = Event.objects.filter(shared_with=request.user).order_by("name")
        relations = (
            Relation.objects.filter(shared_with=request.user)
            .select_related("person", "group", "gift", "event")
            .order_by(
                "person__family_name",
                "person__first_name",
                "group__name",
                "gift__name",
                "event__name",
                "status__status",
            )
        )

        context = {
            "friends": friends,
            "persons": persons,
            "person_groups": person_groups,
            "gifts": gifts,
            "events": events,
            "relations": relations,
        }

        return render(request, self.template_name, context)

    def post(self, request):
        """Process sharing of selected objects."""
        # Get selected friends
        friends = self._get_selected_friends(request)

        # Get selected objects by type
        selection = self._get_selection_from_request(request)

        # Option to share persons in a group
        share_group_persons = "share_group_persons" in request.POST

        # Perform sharing for each object type
        shared_items = {}

        if selection["person_ids"]:
            shared_items["persons"] = self._share_persons(selection["person_ids"], friends)

        if selection["person_group_ids"]:
            shared_items["person_groups"] = self._share_person_groups(
                selection["person_group_ids"], friends, share_members=share_group_persons
            )

        if selection["gift_ids"]:
            shared_items["gifts"] = self._share_gifts(selection["gift_ids"], friends)

        if selection["event_ids"]:
            shared_items["events"] = self._share_events(selection["event_ids"], friends)

        if selection["relation_ids"]:
            shared_items["relations"] = self._share_relations(selection["relation_ids"], friends)

        # Success message
        messages.success(
            request, gettext("Successfully shared items with {} friend(s)").format(len(friends))
        )

        return redirect("gift_manager:share_objects")

    def _get_selected_friends(self, request) -> Sequence[User]:
        """Get selected friends from the request.

        Args:
            request: The HTTP request

        Returns:
            Sequence of selected users
        """
        friend_ids = request.POST.getlist("friends")
        return User.objects.filter(id__in=friend_ids)

    def _get_selection_from_request(self, request) -> dict[str, list[str]]:
        """Get the IDs of selected objects from the request.

        Args:
            request: The HTTP request

        Returns:
            Dictionary containing the IDs of selected objects by type
        """
        return {
            "person_ids": request.POST.getlist("persons"),
            "person_group_ids": request.POST.getlist("person_groups"),
            "gift_ids": request.POST.getlist("gifts"),
            "event_ids": request.POST.getlist("events"),
            "relation_ids": request.POST.getlist("relations"),
        }

    def _share_persons(self, person_ids: list[str], friends: Sequence[User]) -> int:
        """Share selected persons with selected friends.

        Args:
            person_ids: List of person IDs to share
            friends: Sequence of friends to share with

        Returns:
            Number of shared persons
        """
        persons = Person.objects.filter(person_id__in=person_ids)

        for person in persons:
            for friend in friends:
                PersonPermission.objects.get_or_create(
                    user=friend, person=person, defaults={"permission_type": "viewer"}
                )

        return len(persons)

    def _share_person_groups(
        self, person_group_ids: list[str], friends: Sequence[User], *, share_members: bool = False
    ) -> int:
        """Share selected groups with selected friends.

        Args:
            person_group_ids: List of group IDs to share
            friends: Sequence of friends to share with
            share_members: If True, the persons in the groups are also shared

        Returns:
            Number of shared groups
        """
        groups = PersonGroup.objects.filter(group_id__in=person_group_ids)

        for group in groups:
            # Share the group
            for friend in friends:
                PersonGroupPermission.objects.get_or_create(
                    user=friend, group=group, defaults={"permission_type": "viewer"}
                )

            # If requested, also share the persons in the group
            if share_members:
                persons_in_group = group.person_set.all()
                for person in persons_in_group:
                    for friend in friends:
                        PersonPermission.objects.get_or_create(
                            user=friend, person=person, defaults={"permission_type": "viewer"}
                        )

        return len(groups)

    def _share_gifts(self, gift_ids: list[str], friends: Sequence[User]) -> int:
        """Share selected gifts with selected friends.

        Args:
            gift_ids: List of gift IDs to share
            friends: Sequence of friends to share with

        Returns:
            Number of shared gifts
        """
        gifts = Gift.objects.filter(gift_id__in=gift_ids)

        for gift in gifts:
            for friend in friends:
                GiftPermission.objects.get_or_create(
                    user=friend, gift=gift, defaults={"permission_type": "viewer"}
                )

        return len(gifts)

    def _share_events(self, event_ids: list[str], friends: Sequence[User]) -> int:
        """Share selected events with selected friends.

        Args:
            event_ids: List of event IDs to share
            friends: Sequence of friends to share with

        Returns:
            Number of shared events
        """
        events = Event.objects.filter(event_id__in=event_ids)

        for event in events:
            for friend in friends:
                EventPermission.objects.get_or_create(
                    user=friend, event=event, defaults={"permission_type": "viewer"}
                )

        return len(events)

    def _share_relations(self, relation_ids: list[str], friends: Sequence[User]) -> int:
        """Share selected relations with selected friends.

        Includes cascade sharing of related objects.

        Args:
            relation_ids: List of relation IDs to share
            friends: Sequence of friends to share with

        Returns:
            Number of shared relations
        """
        relations = Relation.objects.filter(relation_id__in=relation_ids)

        for relation in relations:
            # Share the relation itself
            for friend in friends:
                RelationPermission.objects.get_or_create(
                    user=friend, relation=relation, defaults={"permission_type": "viewer"}
                )

            # Share the associated gift
            if relation.gift:
                self._share_related_object(relation.gift, friends, GiftPermission)

            # Share the associated person or group
            if relation.person:
                self._share_related_object(relation.person, friends, PersonPermission)
            elif relation.group:
                self._share_related_object(
                    relation.group, friends, PersonGroupPermission, field_name="group"
                )

            # Share the associated event
            if relation.event:
                self._share_related_object(relation.event, friends, EventPermission)

        return len(relations)

    def _share_related_object(
        self,
        obj: SharedObjectType,
        friends: Sequence[User],
        permission_model: ModelType,
        field_name: str = "",
    ) -> None:
        """Utility method to share an object related to a relation.

        Args:
            obj: The object to share
            friends: Sequence of friends to share with
            permission_model: The permission model to use
            field_name: The field name in the permission model (default: class name in lowercase)

        Returns:
            None
        """
        if not field_name:
            field_name = obj.__class__.__name__.lower()

        for friend in friends:
            kwargs = {"user": friend, field_name: obj, "defaults": {"permission_type": "viewer"}}
            permission_model.objects.get_or_create(**kwargs)
