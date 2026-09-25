from django.urls import path
from apps.institutions.views import (
    InstitutionRegisterView,
    InstitutionListView,
    InstitutionDetailView,
    ApproveInstitutionView,
    RejectInstitutionView,
)

urlpatterns = [
    path('register/', InstitutionRegisterView.as_view(), name='institution_register'),
    path('<uuid:id>/', InstitutionDetailView.as_view(), name='institution_detail'),
    path('', InstitutionListView.as_view(), name='institution_list'),
    path('<uuid:id>/approve/', ApproveInstitutionView.as_view(), name='institution_approve'),
    path('<uuid:id>/reject/', RejectInstitutionView.as_view(), name='institution_reject'),
]
