# filepath: /home/adrien/Work/Perso/GiftManager/gift_manager/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView
from django.views.generic import DetailView
from django.views.generic import UpdateView
from django.views.generic.edit import CreateView
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib.auth.models import User
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse

from .models import Person
from .models import Gift
from .models import Event
from .models import PersonPermission
from .models import Relation
from .models import RelationStatus
from .forms import PersonRelationForm
from .forms import GiftRelationForm
from .forms import EventForm


def home(request):
    return render(request, 'gift_manager/home.html')


class FilterByUserMixin:
    def get_queryset(self):
        return self.model.objects.filter(
            Q(shared_with=self.request.user)
        )


class GetObjectByTokenMixin:
    pk_name = None

    def get_object(self, queryset=None):
        queryset = self.get_queryset()
        obj_id = self.kwargs.get("pk")
        if obj_id is None:
            raise Http404("No object found matching the query")
        if self.pk_name is None:
            raise AttributeError("pk_name attribute is required")
        kwargs = {self.pk_name: obj_id}
        return get_object_or_404(queryset, **kwargs)


class PersonListView(LoginRequiredMixin, ListView):
    model = Person
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    column_names = {
        'first_name': 'First Name',
        'family_name': 'Family Name',
        'email_address': 'Email Address',
        'groups': 'Groups',
        'shared_with': 'Shared With'
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Persons'
        context['column_names'] = self.column_names
        return context

    def get_queryset(self):
        """
        Return Persons for the current user or shared with the user.
        """
        return Person.objects.filter(
            Q(shared_with=self.request.user)
        ).values("person_id", *self.column_names)


class PersonCreateView(LoginRequiredMixin, CreateView):
    model = Person
    template_name = "gift_manager/create_form.html"
    fields = ['first_name', 'family_name', 'email_address', 'groups', 'shared_with']
    login_url = "/accounts/login/"
    success_url = reverse_lazy('gift_manager:persons')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Person'
        context["action"] = "Create"
        context['cancel_url'] = reverse_lazy('gift_manager:persons')
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['shared_with'].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields['shared_with'].required = False  # Rendre le champ optionnel dans le formulaire
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Ajouter automatiquement l'utilisateur courant
        if form.cleaned_data['shared_with']:
            form.instance.shared_with.set(form.cleaned_data['shared_with'])
        # PersonPermission.objects.get_or_create(user=self.request.user, person=form.instance.person_id, permission_type='viewer')
        return response


class PersonUpdateView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, UpdateView):
    model = Person
    template_name = "gift_manager/create_form.html"
    fields = ['first_name', 'family_name', 'email_address', 'groups', 'shared_with']
    login_url = "/accounts/login/"
    success_url = reverse_lazy('gift_manager:persons')
    pk_name = "person_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Person'
        context["action"] = "Edit"
        context['cancel_url'] = reverse_lazy('gift_manager:persons')
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['shared_with'].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields['shared_with'].required = False  # Rendre le champ optionnel dans le formulaire
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Ajouter automatiquement l'utilisateur courant
        if form.cleaned_data['shared_with']:
            form.instance.shared_with.set(form.cleaned_data['shared_with'])
        return response


class GiftListView(LoginRequiredMixin, ListView):
    model = Gift
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    column_names = {
        'name': 'Gift Name',
        'comment': 'Comment',
        'tags': 'Tags',
        'shared_with': 'Shared With'
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Gifts'
        context['column_names'] = self.column_names
        return context

    def get_queryset(self):
        """
        Return Gifts for the current user or shared with the user.
        """
        return Gift.objects.filter(
            Q(shared_with=self.request.user)
        ).values("gift_id", *self.column_names)


class GiftCreateView(LoginRequiredMixin, CreateView):
    model = Gift
    template_name = "gift_manager/create_form.html"
    fields = ['name', 'comment', 'tags', 'shared_with']
    login_url = "/accounts/login/"
    success_url = reverse_lazy('gift_manager:gifts')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Gift'
        context["action"] = "Create"
        context['cancel_url'] = reverse_lazy('gift_manager:gifts')
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['shared_with'].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields['shared_with'].required = False  # Rendre le champ optionnel dans le formulaire
        form.fields['tags'].required = False  # Rendre le champ optionnel dans le formulaire
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Ajouter automatiquement l'utilisateur courant
        if form.cleaned_data['shared_with']:
            form.instance.shared_with.set(form.cleaned_data['shared_with'])
        return response


class GiftUpdateView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, UpdateView):
    model = Gift
    template_name = "gift_manager/create_form.html"
    fields = ['name', 'comment', 'tags', 'shared_with']
    login_url = "/accounts/login/"
    success_url = reverse_lazy('gift_manager:gifts')
    pk_name = "gift_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Gift'
        context["action"] = "Edit"
        context['cancel_url'] = reverse_lazy('gift_manager:gifts')
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['shared_with'].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields['shared_with'].required = False  # Rendre le champ optionnel dans le formulaire
        form.fields['tags'].required = False  # Rendre le champ optionnel dans le formulaire
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Ajouter automatiquement l'utilisateur courant
        if form.cleaned_data['shared_with']:
            form.instance.shared_with.set(form.cleaned_data['shared_with'])
        return response


class EventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    column_names = {
        'name': 'Event Name',
        'comment': 'Comment',
        'usual_date': 'Usual date',
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Events'
        context['column_names'] = self.column_names
        return context

    def get_queryset(self):
        """
        Return Events for the current user or shared with the user.
        """
        return Event.objects.filter(
            Q(shared_with=self.request.user)
        ).values("event_id", *self.column_names)


class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    success_url = reverse_lazy('gift_manager:events')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Event'
        context["action"] = "Create"
        context['cancel_url'] = reverse_lazy('gift_manager:events')
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['shared_with'].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields['shared_with'].required = False  # Rendre le champ optionnel dans le formulaire
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Ajouter automatiquement l'utilisateur courant
        if form.cleaned_data['shared_with']:
            form.instance.shared_with.set(form.cleaned_data['shared_with'])
        return response


class EventUpdateView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, UpdateView):
    model = Event
    form_class = EventForm
    template_name = "gift_manager/create_form.html"
    login_url = "/accounts/login/"
    success_url = reverse_lazy('gift_manager:events')
    pk_name = "event_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Event'
        context["action"] = "Edit"
        context['cancel_url'] = reverse_lazy('gift_manager:events')
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['shared_with'].queryset = User.objects.exclude(id=self.request.user.id)
        form.fields['shared_with'].required = False  # Rendre le champ optionnel dans le formulaire
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        form.instance.shared_with.add(self.request.user)  # Ajouter automatiquement l'utilisateur courant
        if form.cleaned_data['shared_with']:
            form.instance.shared_with.set(form.cleaned_data['shared_with'])
        return response


class PersonDetailView(FilterByUserMixin, GetObjectByTokenMixin, LoginRequiredMixin, DetailView):
    model = Person
    template_name = "gift_manager/person_detail.html"
    context_object_name = "person"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    pk_name = "person_id"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['relations'] = Relation.objects.filter(person=self.object)
        context['shared_with'] = self.object.shared_with.exclude(id=self.request.user.id)
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
        context['relations'] = Relation.objects.filter(gift=self.object)
        context['shared_with'] = self.object.shared_with.exclude(id=self.request.user.id)
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
        context['relations'] = Relation.objects.filter(event=self.object)
        context['shared_with'] = self.object.shared_with.exclude(id=self.request.user.id)
        return context


class PersonRelationCreateView(LoginRequiredMixin, CreateView):
    model = Relation
    form_class = PersonRelationForm
    template_name = "gift_manager/create_person_relation_form.html"
    login_url = "/accounts/login/"

    def get_initial(self):
        initial = super().get_initial()
        initial['person'] = self.kwargs['pk']
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['person'] = Person.objects.get(person_id=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        form.instance.person = Person.objects.get(person_id=self.kwargs['pk'])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('gift_manager:person_detail', kwargs={'pk': self.kwargs['pk']})


class GiftRelationCreateView(LoginRequiredMixin, CreateView):
    model = Relation
    form_class = GiftRelationForm
    template_name = "gift_manager/create_gift_relation_form.html"
    login_url = "/accounts/login/"

    def get_initial(self):
        initial = super().get_initial()
        initial['gift'] = self.kwargs['pk']
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['gift'] = Gift.objects.get(gift_id=self.kwargs['pk'])
        return context

    def form_valid(self, form):
        form.instance.gift = Gift.objects.get(gift_id=self.kwargs['pk'])
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('gift_manager:gift_detail', kwargs={'pk': self.kwargs['pk']})


# class RelationStatusListView(LoginRequiredMixin, ListView):
#     model = RelationStatus
#     template_name = "gift_manager/relation_status_list.html"
#     context_object_name = "statuses"
#     login_url = "/accounts/login/"
#     redirect_field_name = "redirect_to"


class RelationStatusListView(LoginRequiredMixin, ListView):
    model = RelationStatus
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    column_names = {
        'status': 'Status',
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Status'
        context['column_names'] = self.column_names
        return context

    def get_queryset(self):
        """
        Return RelationStatus.
        """
        return RelationStatus.objects.values("pk", *self.column_names)


class RelationStatusDetailView(LoginRequiredMixin, DetailView):
    model = RelationStatus
    template_name = "gift_manager/relation_status_detail.html"
    context_object_name = "status"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['relations'] = Relation.objects.filter(status=self.object)
        return context
