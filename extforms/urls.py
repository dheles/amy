from django.conf.urls import url, include

from extforms import views

urlpatterns = [
    # these views create a some sort of workshop-request -
    # a request for SWC, or for DC workshop, or a request for self-organized DC
    # workshop
    url(r'^request_training/$', views.TrainingRequestCreate.as_view(), name='training_request'),
    url(r'^request_training/confirm/$', views.TrainingRequestConfirm.as_view(), name='training_request_confirm'),
    # forms below have been turned off:
    url(r'^swc/request/$', views.SWCEventRequest.as_view(), name='swc_workshop_request'),
    url(r'^dc/request/$', views.DCEventRequest.as_view(), name='dc_workshop_request'),
    url(r'^submit/$', views.EventSubmission.as_view(), name='event_submit'),
    url(r'^dc/request_selforganized/$', views.DCSelfOrganizedEventRequest.as_view(), name='dc_workshop_selforganized_request'),
    url(r'^update_profile/$', views.ProfileUpdateRequestView.as_view(), name='profileupdate_request'),
]
