from django import forms
from .models import Event
from .models import Relation

class PersonRelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ['gift', 'status', 'due_date', 'event']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['event'].queryset = Event.objects.all()
        self.fields['event'].required = False


class GiftRelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ['person', 'status', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }


class EventForm(forms.ModelForm):
    date_type = forms.ChoiceField(choices=[('absolute', 'Absolute Date'), ('recurrence', 'Recurrence')], widget=forms.RadioSelect)

    class Meta:
        model = Event
        fields = ['name', 'comment', 'date_type', 'absolute_date', 'recurrence', 'shared_with']
        widgets = {
            'absolute_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['absolute_date'].required = False
        self.fields['recurrence'].required = False

        if self.instance and self.instance.absolute_date:
            self.fields['date_type'].initial = 'absolute'
        elif self.instance and self.instance.recurrence:
            self.fields['date_type'].initial = 'recurrence'
