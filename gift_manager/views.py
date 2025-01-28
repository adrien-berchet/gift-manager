# filepath: /home/adrien/Work/Perso/GiftManager/gift_manager/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView
from django.views.generic.edit import CreateView
from django.urls import reverse_lazy
from django.db.models import Q
from django.contrib.auth.models import User

from .models import Person
from .models import Gift
from .models import Event
from .models import PersonPermission


def home(request):
    return render(request, 'gift_manager/home.html')


class PersonListView(LoginRequiredMixin, ListView):
    model = Person
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = [field.name for field in Person._meta.fields]
        context['type'] = 'Persons'
        return context

    def get_queryset(self):
        """
        Return Persons for the current user or shared with the user.
        """
        return Person.objects.filter(
            Q(shared_with=self.request.user)
        ).values('first_name', 'family_name', 'email_address').order_by("first_name", "family_name")


class PersonCreateView(LoginRequiredMixin, CreateView):
    model = Person
    template_name = "gift_manager/create_form.html"
    fields = ['first_name', 'family_name', 'email_address', 'groups', 'shared_with']
    login_url = "/accounts/login/"
    success_url = reverse_lazy('gift_manager:persons')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Person'
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


class GiftListView(LoginRequiredMixin, ListView):
    model = Gift
    template_name = "gift_manager/data_list.html"
    context_object_name = "data"
    login_url = "/accounts/login/"
    redirect_field_name = "redirect_to"
    displayed_cols = ['name', 'comment', 'tags', 'shared_with']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = [field.name for field in Gift._meta.fields]
        context['type'] = 'Gifts'
        context['columns'] = self.displayed_cols
        return context

    def get_queryset(self):
        """
        Return Gifts for the current user or shared with the user.
        """
        return Gift.objects.filter(
            Q(shared_with=self.request.user)
        ).values(*self.displayed_cols).order_by("name")

class GiftCreateView(LoginRequiredMixin, CreateView):
    model = Gift
    template_name = "gift_manager/create_form.html"
    fields = ['name', 'comment', 'tags', 'shared_with']
    login_url = "/accounts/login/"
    success_url = reverse_lazy('gift_manager:gifts')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Gift'
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
    displayed_cols = ['name', 'comment', 'usual_date']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = [field.name for field in Event._meta.fields]
        context['type'] = 'Events'
        context['columns'] = self.displayed_cols
        return context

    def get_queryset(self):
        """
        Return Events for the current user or shared with the user.
        """
        return Event.objects.filter(
            Q(shared_with=self.request.user)
        ).values(*self.displayed_cols).order_by("name")

class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    template_name = "gift_manager/create_form.html"
    fields = ['name', 'comment', 'usual_date', 'shared_with']
    login_url = "/accounts/login/"
    success_url = reverse_lazy('gift_manager:events')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type'] = 'Event'
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
