from django.urls import path
from apps.credentials.views import (
    IssueCredentialView,
    IssueBatchCredentialView,
    BatchStatusView,
    CredentialListView,
    CredentialDetailView,
)

urlpatterns = [
    path('', CredentialListView.as_view(), name='credential_list'),
    path('issue/', IssueCredentialView.as_view(), name='credential_issue'),
    path('issue-batch/', IssueBatchCredentialView.as_view(), name='credential_issue_batch'),
    path('issue-batch/<uuid:batch_id>/status/', BatchStatusView.as_view(), name='credential_batch_status'),
    path('<uuid:id>/', CredentialDetailView.as_view(), name='credential_detail'),
]
