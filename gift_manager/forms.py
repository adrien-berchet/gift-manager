from django import forms
from .models import Relation

class PersonRelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ['gift', 'status', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }


class GiftRelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ['person', 'status', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }
