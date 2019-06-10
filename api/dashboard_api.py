from __future__ import print_function
from collections import OrderedDict
from datetime import datetime, timedelta
from json import dumps

from flask import abort, Blueprint, render_template, request, Response

from config.constants import ALL_DATA_STREAMS, REDUCED_API_TIME_FORMAT, data_stream_print
from database.data_access_models import ChunkRegistry
from database.study_models import Study
from database.user_models import Participant
from libs.admin_authentication import authenticate_admin_study_access

dashboard_api = Blueprint('dashboard_api', __name__)

DATETIME_FORMAT_ERROR = \
    "Dates and times provided to this endpoint must be formatted like this: 2010-11-22 (%s)" % REDUCED_API_TIME_FORMAT


@dashboard_api.route("/dashboard/<string:study_id>", methods=["GET"])
@authenticate_admin_study_access
def dashboard_page(study_id=None):
    """ information for the general dashboard view for a study"""
    participants = list(Participant.objects.filter(study=study_id).values_list("patient_id", flat=True))
    return render_template(
        'dashboard/dashboard.html',
        study_name=Study.objects.filter(pk=study_id).values_list("name", flat=True).get(),
        participants=participants,
        study_id=study_id,
        data_stream_print=data_stream_print,
        ALL_DATA_STREAMS=ALL_DATA_STREAMS,
        length=max(len(participants), len(ALL_DATA_STREAMS)),
        print_data=data_stream_print,
    )


@dashboard_api.route("/dashboard/<string:study_id>/data/<string:data_stream>", methods=["GET", "POST"])
@authenticate_admin_study_access
def query_data_for_user_for_data_stream(study_id, data_stream):
    """ parses information for the data stream dashboard view"""
    patient_ids = list(Participant.objects.filter(study=study_id).values_list("patient_id", flat=True))
    patient_ids.sort()
    participant_objects = [get_participant(patient_id, study_id) for patient_id in patient_ids]
    start, end = extract_date_args_from_request()
    minimum, maximum = extract_range_args_from_request()
    stream_data = OrderedDict((participant.patient_id,
                               dashboard_chunkregistry_query(participant.id, data_stream=data_stream))
                              for participant in participant_objects
                              )

    # general data fetching
    first_day, last_day = dashboard_chunkregistry_date_query(study_id)
    if first_day is not None:
        unique_dates, _, _ = get_unique_dates(start, end, first_day, last_day)
        next_url, past_url = create_next_past_urls(first_day, last_day, start=start, end=end)

        # get the byte streams per date for each patient for a specific data stream for those dates
        byte_streams = OrderedDict(
            (patient_id, [
                get_bytes_participant_match(stream_data[patient_id], date) for date in unique_dates
            ]) for patient_id in patient_ids
        )
        # check if there is data to display
        check_if_empty = [data for patient in byte_streams.keys() for data in byte_streams[patient] if data is not None]

    if first_day is None or (len(check_if_empty) == 0 and past_url == ""):
        unique_dates = []
        next_url = ""
        past_url = ""
        byte_streams = {}

    return render_template(
        'dashboard/data_stream_dash.html',
        study_name=Study.objects.filter(pk=study_id).values_list("name", flat=True).get(),
        data_stream=data_stream_print.get(data_stream),
        times=unique_dates,
        byte_streams=byte_streams,
        base_next_url=next_url,
        base_past_url=past_url,
        patient_ids=patient_ids,
        study_id=study_id,
        data_stream_print=data_stream_print,
        ALL_DATA_STREAMS=ALL_DATA_STREAMS,
        max=maximum,
        min=minimum,
        first_day=first_day,
        last_day=last_day,
    )


@dashboard_api.route("/dashboard/<string:study_id>/patient/<string:patient_id>", methods=["GET"])
@authenticate_admin_study_access
def query_data_for_user(study_id, patient_id):
    """ parses data to be displayed for the singular participant dashboard view """
    participant = get_participant(patient_id, study_id)
    start, end = extract_date_args_from_request()
    chunks = dashboard_chunkregistry_query(participant.id)
    patient_ids = list(Participant.objects
                       .filter(study=study_id)
                       .exclude(patient_id=patient_id)
                       .values_list("patient_id", flat=True)
                       )

    # create a list of all the unique days in which data was recorded for this study
    if chunks:
        first_day, last_day = dashboard_chunkregistry_date_query(study_id)
        unique_dates, first_date_data_entry, last_date_data_entry = \
            get_unique_dates(start, end, first_day, last_day, chunks)
        next_url, past_url = create_next_past_urls(first_day, last_day, start=start, end=end)

        # get the byte data for the dates that have data collected in that week
        byte_streams = OrderedDict(
            (stream, [
                get_bytes_data_stream_match(chunks, date, stream) for date in unique_dates
            ]) for stream in ALL_DATA_STREAMS
        )
    else:  # edge case if no data has been entered
        byte_streams = {}
        unique_dates = []
        next_url = ""
        past_url = ""
        first_day = 0
        last_day = 0
        first_date_data_entry = ""
        last_date_data_entry = ""

    return render_template(
        'dashboard/participant_dash.html',
        participant=participant,
        times=unique_dates,
        byte_streams=byte_streams,
        next_url=next_url,
        past_url=past_url,
        patient_ids=patient_ids,
        study_id=study_id,
        first_day=first_day,
        last_day=last_day,
        first_date_data=first_date_data_entry,
        last_date_data=last_date_data_entry,
        data_stream_print=data_stream_print,
        ALL_DATA_STREAMS=ALL_DATA_STREAMS
    )


def get_unique_dates(start, end, first_day, last_day, chunks=None):
    """ create a list of all the unique days in which data was recorded for this study """
    first_date_data_entry = None
    last_date_data_entry = None
    if chunks:
        all_dates = list(set(
            (chunk["time_bin"]).date() for chunk in chunks)
        )
        all_dates.sort()

        # create a list of all of the valid days in this study
        first_date_data_entry = all_dates[0]
        last_date_data_entry = all_dates[-1]

    # validate start date is before end date
    if (start and end) and (end.date() - start.date()).days < 0:
        temp = start
        start = end
        end = temp

    # unique_dates is all of the dates for the week we are showing
    if start is None: # if start is none default to beginning
        end_num = min((last_day - first_day).days + 1, 7)
        unique_dates = [(first_day + timedelta(days=date)) for date in range(end_num)]
    elif end is None:  # if end if none default to 7 days
        end_num = min((last_day - start.date()).days + 1, 7)
        unique_dates = [(start.date() + timedelta(days=date)) for date in range(end_num)]
    elif (start.date() - first_day).days < 0:
        # this is the edge case for out of bounds at beginning to keep the duration the same
        end_num = (end.date() - first_day).days + 1
        unique_dates = [(first_day + timedelta(days=date)) for date in range(end_num)]
    elif (last_day - end.date()).days < 0:
        # this is the edge case for out of bounds at end to keep the duration the same
        end_num = (last_day - start.date()).days + 1
        unique_dates = [(start.date() + timedelta(days=date)) for date in range(end_num)]
    else:  # this is if they specify both start and end
        end_num = (end.date() - start.date()).days + 1
        unique_dates = [(start.date() + timedelta(days=date)) for date in range(end_num)]

    return unique_dates, first_date_data_entry, last_date_data_entry


def create_next_past_urls(first_day, last_day, start=None, end=None):
    """ set the URLs of the next/past pages for patient and data stream dashboard """
    # note: in the "if" cases, the dates are intentionally allowed outside the data collection date
    # range so that the duration stays the same if you page backwards instead of resetting
    # to the number currently shown

    if start and end:
        duration = (end.date() - start.date()).days
    else:
        duration = 7
        start = datetime.combine(first_day, datetime.min.time())
        end = datetime.combine(first_day + timedelta(days=7), datetime.min.time())

    if 0 < (start.date() - first_day).days < duration:
        past_url = "?start=" + (start.date() - timedelta(days=(duration + 1))).strftime(REDUCED_API_TIME_FORMAT) + \
                   "&end=" + (start.date() - timedelta(days=1)).strftime(REDUCED_API_TIME_FORMAT)

    elif (start.date() - first_day).days <= 0:
        past_url = ""
    else:
        past_url = "?start=" + (start.date() - timedelta(days=duration + 1)).strftime(REDUCED_API_TIME_FORMAT) + \
                    "&end=" + (start.date() - timedelta(days=1)).strftime(REDUCED_API_TIME_FORMAT)
    if (last_day - timedelta(days=duration + 1)) < end.date() < (last_day - timedelta(days=1)):
        next_url = "?start=" + (end.date() + timedelta(days=1)).strftime(REDUCED_API_TIME_FORMAT) + "&end=" + \
                   (end.date() + timedelta(days=(duration + 1))).strftime(REDUCED_API_TIME_FORMAT)
    elif (last_day - end.date()).days <= 0:
        next_url = ""
    else:
        next_url = "?start=" + \
                   (start.date() + timedelta(days=duration + 1)).strftime(REDUCED_API_TIME_FORMAT) + "&end=" + \
                   (end.date() + timedelta(days=duration + 1)).strftime(REDUCED_API_TIME_FORMAT)
    return next_url, past_url


def get_bytes_participant_match(stream_data, date):
    all_bytes = None
    for data_point in stream_data:
        if (data_point["time_bin"]).date() == date:
            if all_bytes is None:
                all_bytes = data_point["bytes"]
            else:
                all_bytes += data_point["bytes"]
    if all_bytes is not None:
        return all_bytes
    else:
        return None


def get_bytes_data_stream_match(chunks, date, stream):
    """ returns byte value for correct chunk based on data stream and type comparisons"""
    all_bytes = None
    for chunk in chunks:
        if (chunk["time_bin"]).date() == date and chunk["data_stream"] == stream:
            if all_bytes is None:
                all_bytes = chunk["bytes"]
            else:
                all_bytes += chunk["bytes"]
    if all_bytes is not None:
        return all_bytes
    else:
        return None


def dashboard_chunkregistry_date_query(study_id, data_stream=None):
    kwargs = {"study_id": study_id}
    if data_stream:
        kwargs["data_type"] = data_stream
    first = ChunkRegistry.objects.filter(**kwargs).values_list("time_bin", flat=True).first()
    last = ChunkRegistry.objects.filter(**kwargs).values_list("time_bin", flat=True).last()
    if first is None or last is None:
        return None, None
    else:
        return first.date(), last.date()


def dashboard_chunkregistry_query(participant_id, data_stream=None, start=None, end=None):
    """ Queries ChunkRegistry based on the provided parameters and returns a list of dictionaries
    with 3 keys: bytes, data_stream, and time_bin. """
    kwargs = {"participant__id": participant_id}
    if start:
        kwargs["time_bin__gte"] = start
    if end:
        kwargs["time_bin__lte"] = end
    if data_stream:
        kwargs["data_type"] = data_stream

    # on a (good) test device running on sqlite, for 12,200 chunks, this takes ~135ms
    # sticking the query_set directly into a list is a slight speedup. (We need it all in memory anyway.)
    chunks = list(
        ChunkRegistry.objects.filter(**kwargs)
        .extra(
            select={
                # rename the data_type and file_size fields in the db query itself for speed
                'data_stream': 'data_type',
                'bytes': 'file_size',
            }
        ).values("bytes", "data_stream", "time_bin")
    )

    return chunks


def extract_date_args_from_request():
    """ Gets start and end arguments from GET/POST params, throws 400 on date formatting errors. """
    start = request.values.get("start", None)
    end = request.values.get("end", None)
    try:
        if start:
            start = datetime.strptime(start, REDUCED_API_TIME_FORMAT)
        if end:
            end = datetime.strptime(end, REDUCED_API_TIME_FORMAT)
    except ValueError as e:
        return abort(400, DATETIME_FORMAT_ERROR)

    return start, end

def extract_range_args_from_request():
    """ Gets minimum and maximum arguments from GET/POST params, throws ?? formatting errors. """
    minimum = request.values.get("minimum", None)
    maximum = request.values.get("maximum", None)

    return minimum, maximum


def extract_data_stream_args_from_request():
    """ Gets data stream if it is provided as a request POST or GET parameter,
    throws 400 errors on unknown data streams. """
    data_stream = request.values.get("data_stream", None)
    if data_stream:
        if data_stream not in ALL_DATA_STREAMS:
            return abort(400, "unrecognized data stream '%s'" % data_stream)
    return data_stream


def get_participant(patient_id, study_id):
    """ Just factoring out a common abort operation. """
    try:
        return Participant.objects.get(study=study_id, patient_id=patient_id)
    except Participant.DoesNotExist:
        # 2 useful error messages
        if not Participant.objects.get(patient_id=patient_id).exists():
            return abort(400, "No such user exists.")
        else:
            return abort(400, "No such user exists in this study.")

