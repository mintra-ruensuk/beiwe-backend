from __future__ import print_function

from datetime import datetime, timedelta
from json import dumps
from pprint import pprint

from flask import abort, Blueprint, render_template, request, Response

from config.constants import ALL_DATA_STREAMS, REDUCED_API_TIME_FORMAT
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
    # participants needs to be json serializable, need to dump queryset into a list.
    participants = list(Participant.objects.filter(study=study_id).values_list("patient_id", flat=True))
    return render_template(
        'dashboard/dashboard.html',
        study_name=Study.objects.filter(pk=study_id).values_list("name", flat=True).get(),
        participants=participants,
        study_id=study_id,
    )

@dashboard_api.route("/dashboard/<string:study_id>/<string:patient_id>/<string:data_stream>", methods=["GET", "POST"])
@authenticate_admin_study_access
def query_data_for_user_for_data_stream(study_id, patient_id, data_stream):
    participant = get_participant(patient_id, study_id)
    start, end = extract_date_args_from_request()
    data = dashboard_chunkregistry_query(participant.id, data_stream=data_stream, start=start, end=end)
    return Response(dumps(data), mimetype="text/json")

@dashboard_api.route("/dashboard/<string:study_id>/patient/<string:patient_id>", methods=["GET"])
@authenticate_admin_study_access
def query_data_for_user(study_id, patient_id):

    # general data fetching
    participant = get_participant(patient_id, study_id)
    start, end = extract_date_args_from_request()
    data_stream = extract_data_stream_args_from_request()
    chunks = dashboard_chunkregistry_query(participant.id, data_stream=data_stream)
    participants = list(Participant.objects.filter(study=study_id).values_list("patient_id", flat=True))

    # get a list of all participants not including the current one
    participants = [p for p in participants if p != participant.patient_id]

    # create a list of all the unique days in which data was recorded for this study
    if len(chunks):
        unique_times = list(set(
            (t["time_bin"]).date() for t in chunks)
        )
        unique_times.sort()

        # create a list of all of the valid days in this study
        first_day = unique_times[0]
        last_day = unique_times[-1]
        total_days = []
        for day in range((last_day - first_day).days + 1):
            total_days.append(first_day + timedelta(days=day))

        # set the start and end dates based on the start value given
        if start is None:
            start_num = 0
            if len(total_days) < 8:
                end_num = len(total_days) - 1
            else:
                end_num = 6
        else:
            start_num = total_days.index(start.date())
            if start_num > len(total_days) - 8:
                end_num = len(total_days) - 1
            else:
                end_num = start_num + 6

        # create list of either -1 or date objects for the current dates selected
        # ALSO create a list of all dates to be displayed so that we can display the date even if it is -1
        # (indicating that it should be greyed out)
        display_times = []
        all_times = []
        for date in range(end_num - start_num + 1):
            all_times.append(total_days[start_num + date])
            if total_days[start_num + date] in unique_times:
                display_times.append(total_days[start_num + date])
            else:
                display_times.append(-1)

        # get the next and past urls
        next_url, past_url = make_url(start_num, end_num, total_days)

        # get the byte data for the dates that have data collected in that week
        byte_streams = {
            stream: [
                get_bytes(chunks, stream, time) for time in display_times
            ] for stream in ALL_DATA_STREAMS
        }
    else:  # edge case if no data has been entered
        byte_streams = {}
        display_times = []
        next_url = ""
        past_url = ""
        first_day = 0
        last_day = 0
        all_times = []

    return render_template(
        'dashboard/participant_dash.html',
        participant=participant,
        times=display_times,
        byte_streams=byte_streams,
        next_url=next_url,
        past_url=past_url,
        participants=participants,
        study_id=study_id,
        first_day=first_day,
        last_day=last_day,
        all_times=all_times,
        length=len(all_times),
    )

def make_url(start_num, end_num, total_days):
    # set the URLs of the next/past pages
    if 0 < start_num < 7:
        past_url = "?start=" + (total_days[0]).strftime(REDUCED_API_TIME_FORMAT)
    elif start_num == 0:
        past_url = ""
    elif end_num - start_num < 7:
        past_url = "?start=" + (total_days[start_num - 7]).strftime(REDUCED_API_TIME_FORMAT)
    else:
        past_url = "?start=" + (total_days[start_num - 7]).strftime(REDUCED_API_TIME_FORMAT)
    if len(total_days) - 8 < end_num < len(total_days) - 1:
        next_url = "?start=" + (total_days[end_num + 1]).strftime(REDUCED_API_TIME_FORMAT)
    elif end_num == len(total_days) -1:
        next_url = ""
    else:
        next_url = "?start=" + \
                   (total_days[start_num + 7]).strftime(REDUCED_API_TIME_FORMAT)
    return next_url, past_url


def get_url(time, full_times):
    start_num = full_times.index(time)
    if start_num > len(full_times) - 8:
        diff = (len(full_times) - 1) - start_num
        return "?start=" + full_times[start_num].strftime(REDUCED_API_TIME_FORMAT) \
            + "&end=" + full_times[start_num + diff].strftime(REDUCED_API_TIME_FORMAT)
    return "?start=" + full_times[start_num].strftime(REDUCED_API_TIME_FORMAT) \
        + "&end=" + full_times[start_num + 6].strftime(REDUCED_API_TIME_FORMAT)


def get_bytes(chunks, stream, time):
    """ returns byte value for correct chunk based on data stream and type comparisons"""
    all_bytes = None
    if time == -1:
        return -1
    for chunk in chunks:
        if (chunk["time_bin"]).date() == time and chunk["data_stream"] == stream:
            if all_bytes is None:
                all_bytes = chunk["bytes"]
            else:
                all_bytes += chunk["bytes"]
    if all_bytes is not None:
        return all_bytes
    else:
        return -1

def dashboard_chunkregistry_query(participant_id, data_stream=None, start=None, end=None):
    """ Queries ChunkRegistry based on the provided parameters and returns a list of dictionaries
    with 3 keys: bytes, data_stream, and time_bin. """

    args = {"participant__id": participant_id}
    if start:
        args["time_bin__gte"] = start
    if end:
        args["time_bin__lte"] = end
    if data_stream:
        args["data_type"] = data_stream

    # on a (good) test device running on sqlite, for 12,200 chunks, this takes ~135ms
    # sticking the query_set directly into a list is a slight speedup. (We need it all in memory anyway.)
    chunks = list(
        ChunkRegistry.objects.filter(**args)
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

