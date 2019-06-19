from __future__ import print_function
from collections import OrderedDict
from datetime import datetime, timedelta, date

from flask import abort, Blueprint, render_template, request

from database.study_models import Study, DashboardColorSetting, DashboardGradient, DashboardInflection
from config.constants import ALL_DATA_STREAMS, REDUCED_API_TIME_FORMAT, data_stream_dict, processed_data_stream_dict
from database.data_access_models import ChunkRegistry, PipelineRegistry
from database.user_models import Participant
from libs.admin_authentication import authenticate_admin_study_access
import json

dashboard_api = Blueprint('dashboard_api', __name__)

DATETIME_FORMAT_ERROR = \
    "Dates and times provided to this endpoint must be formatted like this: 2010-11-22 (%s)" % REDUCED_API_TIME_FORMAT


@dashboard_api.route("/dashboard/<string:study_id>", methods=["GET"])
@authenticate_admin_study_access
def dashboard_page(study_id):
    """ information for the general dashboard view for a study"""
    participants = list(Participant.objects.filter(study=study_id).values_list("patient_id", flat=True))
    return render_template(
        'dashboard/dashboard.html',
        study_name=Study.objects.filter(pk=study_id).values_list("name", flat=True).get(),
        participants=participants,
        study_id=study_id,
        data_stream_dict=data_stream_dict,
        processed_data_stream_dict=processed_data_stream_dict,
    )


@dashboard_api.route("/dashboard/<string:study_id>/processed/<string:data_stream>", methods=["GET", "POST"])
@authenticate_admin_study_access
def query_data_for_processed_data(study_id, data_stream):
    """ parses information for the data stream dashboard for the processed data
        note: both of the processed data dashboards require lots of parseing to extract the dates. Thus, neither of
        them are allowed to iterate outside of the range for which they have data recorded, even if there is data for
        other participants/data streams within the study outside of those date ranges.
    """
    study = get_study_or_404(study_id)

    # -------------------------- for a POST request --------------------------------------
    if request.method == "POST":
        color_low_range, color_high_range, all_flags_list = set_default_settings_post_request(study, data_stream)
        show_color = "true"

    # ------------------ below is for a GET request - POST requests will ALSO run this code! ------------------------
    else:
        color_low_range, color_high_range, show_color = extract_range_args_from_request()
        all_flags_list = extract_flag_args_from_request()

    # if it's a post request the defaultcolorsetting will exist and if it's a get request the else will have happened
    # and thus color_low_range, color_high_range, show_color, all_flags_list will exist as well
    if DashboardColorSetting.objects.filter(data_type=data_stream, study=study).exists():
        settings = DashboardColorSetting.objects.get(data_type=data_stream, study=study)
        default_filters = DashboardColorSetting.get_dashboard_color_settings(settings)
        gradient_info = default_filters["gradient"]
        inflection_info = default_filters["inflections"]
        if all_flags_list == [] and color_high_range is None and color_low_range is None:
            # since none of the filters are set, parse default filters to pass in the default settings
            # set the values for gradient filter
            color_low_range = gradient_info["color_range_min"]
            color_high_range = gradient_info["color_range_max"]
            show_color = "true"

            # set the values for the flag/inflection filter*s*
            # the html is expecting a list of lists for the flags [[operator, value], ... ]
            all_flags_list = []
            for flag_info in inflection_info:
                single_flag = [flag_info["operator"].encode("utf-8"), flag_info["inflection_point"]]
                all_flags_list.append(single_flag)

    # change the url params from jinja t/f to python understood T/F
    if show_color == "true":
        show_color = True
    elif show_color == "false":
        show_color = False

    # general data fetching
    # fetch a bunch of data
    participant_objects = Participant.objects.filter(study=study_id).order_by("patient_id")
    start, end = extract_date_args_from_request()
    first_day, last_day, stream_data = parse_processed_data(study_id, participant_objects, data_stream)
    unique_dates = []
    next_url = ""
    past_url = ""
    byte_streams = {}
    data_exists = None
    if first_day is not None:
        unique_dates, _, _ = get_unique_dates(start, end, first_day, last_day)
        next_url, past_url = create_next_past_urls(first_day, last_day, start=start, end=end)

        # get the byte streams per date for each patient for a specific data stream for those dates
        byte_streams = OrderedDict(
            (participant.patient_id, [
                get_bytes_processed_data_match(stream_data[participant.patient_id], date) for date in unique_dates
            ]) for participant in participant_objects
        )
        # check if there is data to display
        data_exists = len(
            [data for patient in byte_streams.keys() for data in byte_streams[patient] if data is not None]) > 0

    # this has to exist bc you have to double check for the data_stream dashes but not the patient dashes
    if first_day is None or (not data_exists and past_url == ""):
        unique_dates = []
        next_url = ""
        past_url = ""
        byte_streams = {}

    return render_template(
        'dashboard/processed_datastream_dashboard.html',
        study_name=study.name,
        data_stream=processed_data_stream_dict.get(data_stream),
        times=unique_dates,
        byte_streams=byte_streams,
        base_next_url=next_url,
        base_past_url=past_url,
        study_id=study_id,
        processed_data_stream_dict=processed_data_stream_dict,
        color_low_range=color_low_range,
        color_high_range=color_high_range,
        first_day=first_day,
        last_day=last_day,
        show_color=show_color,
        all_flags_list=all_flags_list,
    )


@dashboard_api.route("/dashboard/<string:study_id>/processed_patient/<string:patient_id>", methods=["GET", "POST"])
@authenticate_admin_study_access
def query_data_for_patient_processed_data(study_id, patient_id):
    """ parses PROCESSED data to be displayed for the singular participant dashboard view
        note: both of the processed data dashboards require lots of parseing to extract the dates. Thus, neither of
        them are allowed to iterate outside of the range for which they have data recorded, even if there is data for
        other participants/data streams within the study outside of those date ranges.
    """
    # query for some general data
    participant = get_participant(patient_id, study_id)
    start, end = extract_date_args_from_request()
    patient_ids = list(Participant.objects
                       .filter(study=study_id)
                       .exclude(patient_id=patient_id)
                       .values_list("patient_id", flat=True)
                       )

    # get the processed data for a specific patient
    # all_data is a list of dicts [{"time_bin": , "stream": , "processed_data": }...]
    first_date_data_entry, last_date_data_entry, all_data = parse_patient_processed_data(study_id, participant)

    # create a list of all the unique days in which data was recorded for this study
    if all_data:
        unique_dates, _, _ = get_unique_dates(start, end, first_date_data_entry, last_date_data_entry)
        next_url, past_url = create_next_past_urls(first_date_data_entry, last_date_data_entry, start=start, end=end)

        # get the byte data for the dates that have data collected in that week
        byte_streams = OrderedDict(
            (stream, [
                get_bytes_patient_processed_match(all_data, date, stream) for date in unique_dates
            ]) for stream in processed_data_stream_dict.keys()
        )
    else:  # edge case if no data has been entered
        byte_streams = {}
        unique_dates = []
        next_url = ""
        past_url = ""
        first_date_data_entry = ""
        last_date_data_entry = ""

    return render_template(
        'dashboard/processed_participant_dashboard.html',
        participant=participant,
        times=unique_dates,
        byte_streams=byte_streams,
        next_url=next_url,
        past_url=past_url,
        patient_ids=patient_ids,
        study_id=study_id,
        first_date_data=first_date_data_entry,
        last_date_data=last_date_data_entry,
        data_stream_dict=processed_data_stream_dict,
    )


@dashboard_api.route("/dashboard/<string:study_id>/data_stream/<string:data_stream>", methods=["GET", "POST"])
@authenticate_admin_study_access
def get_data_for_dashboard_datastream_display(study_id, data_stream):
    """ parses information for the data stream dashboard view GET and POST requests"""
    study = get_study_or_404(study_id)

    # -------------------------- for a POST request --------------------------------------
    if request.method == "POST":
        color_low_range, color_high_range, all_flags_list = set_default_settings_post_request(study, data_stream)
        show_color = "true"

    # ------------------ below is for a GET request - POST requests will ALSO run this code! ------------------------
    else:
        color_low_range, color_high_range, show_color = extract_range_args_from_request()
        all_flags_list = extract_flag_args_from_request()
    participant_objects = Participant.objects.filter(study=study_id).order_by("patient_id")
    default_filters = ""
    if DashboardColorSetting.objects.filter(data_type=data_stream, study=study).exists():
        settings = DashboardColorSetting.objects.get(data_type=data_stream, study=study)
        default_filters = DashboardColorSetting.get_dashboard_color_settings(settings)

    start, end = extract_date_args_from_request()
    stream_data = OrderedDict((participant.patient_id,
                               dashboard_chunkregistry_query(participant.id, data_stream=data_stream))
                              for participant in participant_objects
                              )

    # test if there are default settings saved,
    # and if there are, test if the default filters should be used or if the user has overridden them
    if default_filters != "":
        gradient_info = default_filters["gradient"]
        inflection_info = default_filters["inflections"]
        if all_flags_list == [] and color_high_range is None and color_low_range is None:
            # since none of the filters are set, parse default filters to pass in the default settings
            # set the values for gradient filter
            color_low_range = gradient_info["color_range_min"]
            color_high_range = gradient_info["color_range_max"]
            show_color = "true"

            # set the values for the flag/inflection filter*s*
            # the html is expecting a list of lists for the flags [[operator, value], ... ]
            all_flags_list = []
            for flag_info in inflection_info:
                single_flag = [flag_info["operator"].encode("utf-8"), flag_info["inflection_point"]]
                all_flags_list.append(single_flag)

    # change the url params from jinja t/f to python understood T/F
    if show_color == "true":
        show_color = True
    elif show_color == "false":
        show_color = False

    # general data fetching
    first_day, last_day = dashboard_chunkregistry_date_query(study_id)
    unique_dates = []
    next_url = ""
    past_url = ""
    byte_streams = {}
    data_exists = False
    if first_day is not None:
        unique_dates, _, _ = get_unique_dates(start, end, first_day, last_day)
        next_url, past_url = create_next_past_urls(first_day, last_day, start=start, end=end)

        # get the byte streams per date for each patient for a specific data stream for those dates
        byte_streams = OrderedDict(
            (participant.patient_id, [
                get_bytes_participant_match(stream_data[participant.patient_id], date) for date in unique_dates
            ]) for participant in participant_objects
        )
        # check if there is data to display
        data_exists = len([data for patient in byte_streams.keys() for data in byte_streams[patient] if data is not None]) > 0

    if first_day is None or (not data_exists and past_url == ""):
        unique_dates = []
        next_url = ""
        past_url = ""
        byte_streams = {}

    return render_template(
        'dashboard/data_stream_dashboard.html',
        study_name=study.name,
        data_stream=data_stream_dict.get(data_stream),
        times=unique_dates,
        byte_streams=byte_streams,
        base_next_url=next_url,
        base_past_url=past_url,
        study_id=study_id,
        data_stream_dict=data_stream_dict,
        color_low_range=color_low_range,
        color_high_range=color_high_range,
        first_day=first_day,
        last_day=last_day,
        show_color=show_color,
        all_flags_list=all_flags_list,
    )


@dashboard_api.route("/dashboard/<string:study_id>/patient/<string:patient_id>", methods=["GET"])
@authenticate_admin_study_access
def get_data_for_dashboard_patient_display(study_id, patient_id):
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
        'dashboard/participant_dashboard.html',
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
        data_stream_dict=data_stream_dict,
    )


def parse_processed_data(study_id, participant_objects, data_stream):
    """
    get a list of dicts (pipeline_chunks) of the patient's data and extract the data for the data stream we want
    stream_data = OrderedDict(participant.patient_id: {"time_bin":time_bin, "processed_data": processed_data}, ...)
    this structure is similar to the stream_data structure in get_data_for_dashboard_data_stream_display
    since they perform similar functions
    """
    first = True
    data_exists = False
    first_day = None
    last_day = None
    stream_data = OrderedDict()
    for participant in participant_objects:
        pipeline_chunks = dashboard_pipelineregistry_query(study_id, participant.id)
        list_of_dicts_data = []
        if pipeline_chunks is not None:
            for chunk in pipeline_chunks:
                if data_stream in chunk.keys() and "day" in chunk.keys() and chunk[data_stream] != "NA":
                    time_bin = datetime.strptime(chunk["day"].encode("utf-8"), REDUCED_API_TIME_FORMAT).date()
                    data_exists = True
                    if first:
                        first_day = time_bin
                        last_day = time_bin
                        first = False
                    else:
                        if (time_bin - first_day).days < 0:
                            first_day = time_bin
                        elif (time_bin - last_day).days > 0:
                            last_day = time_bin
                    # check to see if the data should be a float or an int
                    if chunk[data_stream].encode("utf-8").find(".") == -1:
                        processed_data = int(chunk[data_stream])
                    else:
                        processed_data = float(chunk[data_stream])
                    list_of_dicts_data.append({"time_bin": time_bin, "processed_data": processed_data})

        stream_data[participant.patient_id] = None if not data_exists else list_of_dicts_data
        data_exists = False  # you need to reset this
    return first_day, last_day, stream_data


def parse_patient_processed_data(study_id, participant):
    """    create a list of dicts of processed data for one patient.
    [{"time_bin": , "processed_data": , "data_stream": ,}...]
    if there is no data for a patient, first_day and last_day will be None, and all_data will be an empty list
    """
    first = True
    first_day = None
    last_day = None
    pipeline_chunks = dashboard_pipelineregistry_query(study_id, participant.id)
    all_data = []
    if pipeline_chunks is not None:
        for chunk in pipeline_chunks:
            if "day" in chunk.keys():
                time_bin = datetime.strptime(chunk["day"].encode("utf-8"), REDUCED_API_TIME_FORMAT).date()
                if first:
                    first_day = time_bin
                    last_day = time_bin
                    first = False
                else:
                    if (time_bin - first_day).days < 0:
                        first_day = time_bin
                    elif (time_bin - last_day).days > 0:
                        last_day = time_bin
                for stream_key in chunk.keys():
                    if stream_key in processed_data_stream_dict and chunk[stream_key] != "NA":
                        if chunk[stream_key].encode("utf-8").find(".") == -1:
                            processed_data = int(chunk[stream_key])
                        else:
                            processed_data = float(chunk[stream_key])
                        all_data.append({"time_bin": time_bin, "processed_data": processed_data, "data_stream": stream_key})
    return first_day, last_day, all_data


def set_default_settings_post_request(study, data_stream):
    # get all of the variables
    all_flags_list = request.form.get("all_flags_list", "[]")
    color_high_range = request.form.get("color_high_range", 0)
    color_low_range = request.form.get("color_low_range", 0)

    # convert parameters from unicode to correct types
    all_flags_list = json.loads(all_flags_list)
    color_high_range = int(json.loads(color_high_range))
    color_low_range = int(json.loads(color_low_range))

    # make the operator a string
    for flag in all_flags_list:
        flag[0] = flag[0].encode("utf-8")

    # try to get a DashboardColorSetting object and check if it exists
    if DashboardColorSetting.objects.filter(data_type=data_stream, study=study).exists():
        # in this case, a default settings model already exists
        # now we delete the inflections associated with it
        settings = DashboardColorSetting.objects.get(data_type=data_stream, study=study)
        settings.inflections.all().delete()

        # create new gradient
        gradient_variable, _ = DashboardGradient.objects.get_or_create(dashboard_color_setting=settings)
        gradient_variable.color_range_max = color_high_range
        gradient_variable.color_range_min = color_low_range
        gradient_variable.save()

        # create new inflections
        for flag in all_flags_list:
            # all_flags_list looks like this: [[operator, inflection_point], ...]
            inflection_var = DashboardInflection.objects.create(dashboard_color_setting=settings, operator=flag[0])
            inflection_var.operator = flag[0]
            inflection_var.inflection_point = flag[1]
            inflection_var.save()
        settings.save()
    else:
        # this is the case if a default settings does not yet exist
        # create a new dashboard color setting in memory
        settings = DashboardColorSetting.objects.create(data_type=data_stream, study=study)

        # create new gradient
        gradient_variable = DashboardGradient.objects.create(dashboard_color_setting=settings)
        gradient_variable.color_range_max = color_high_range
        gradient_variable.color_range_min = color_low_range

        # create new inflections
        for flag in all_flags_list:
            inflection_var = DashboardInflection.objects.create(dashboard_color_setting=settings, operator=flag[0])
            inflection_var.operator = flag[0]
            inflection_var.inflection_point = flag[1]

        # save the dashboard color setting to the backend (currently is just in memory)
        settings.save()

    return color_low_range, color_high_range, all_flags_list


def get_study_or_404(study_id):
    try:
        return Study.objects.get(pk=study_id)
    except Study.DoesNotExist:
        return abort(404)


def get_unique_dates(start, end, first_day, last_day, chunks=None):
    """ create a list of all the unique days in which data was recorded for this study """
    first_date_data_entry = None
    last_date_data_entry = None
    if chunks:
        all_dates = list(set(
            chunk["time_bin"].date() for chunk in chunks if chunk["time_bin"].date() >= first_day)
            # must be >= first day bc there are some point for 1970 that get filtered out bc obv are garbage
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


def get_bytes_processed_data_match(participant_data, date):
    # participant_data is a list of dicts which hold {time_bin: , processed_data: }
    # there should only ever be one data_point corresponding to a specific date per patient
    # if no data exists, return None -- if the participant_data object is none, there is no data for this data
    # stream for this participant
    if participant_data is not None:
        for data_point in participant_data:
            if(data_point["time_bin"]) == date:
                return data_point["processed_data"]
    return None


def get_bytes_patient_processed_match(participant_data, date, stream):
    # participant_data is a list of dicts which hold {time_bin: , processed_data: , stream:, }
    # there should only ever be one data_point corresponding to a specific date per patient
    # if no data exists, return None -- if the participant_data object is none, there is no data for this data
    # stream for this participant
    if participant_data is not None:
        for data_point in participant_data:
            if(data_point["time_bin"]) == date and data_point["data_stream"] == stream:
                return data_point["processed_data"]
    return None


def dashboard_chunkregistry_date_query(study_id, data_stream=None):
    """ gets the first and last days in the study excluding 1/1/1970 bc that is obviously an error and makes
    the frontend annoying to use """
    kwargs = {"study_id": study_id}
    if data_stream:
        kwargs["data_type"] = data_stream
    first = ChunkRegistry.objects.filter(**kwargs).exclude(time_bin__date=date(1970, 1, 1)).order_by("time_bin").values_list("time_bin", flat=True).first()
    last = ChunkRegistry.objects.filter(**kwargs).order_by("time_bin").values_list("time_bin", flat=True).last()
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


def dashboard_pipelineregistry_query(study_id, participant_id):
    """ Queries Pipeline based on the provided parameters and returns a list of dicts with
    an id (which is ignored), a "day", and a bunch of strings which are data streams """
    # pipeline_chunks looks like this: [{day: 3/4/4, "data_stream1": 36634, "data_stream2": 2525}, ... ]
    pipeline_data = PipelineRegistry.objects.filter(study_id=study_id, participant__id=participant_id).order_by(
        "uploaded_at").last()
    if pipeline_data is not None:
        pipeline_chunks = json.loads(json.dumps(pipeline_data.processed_data)) # I feel like this shouldn't work but idk
        if pipeline_chunks:
            return pipeline_chunks

    return None


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
    """ Gets minimum and maximum arguments from GET/POST params """
    color_low_range = request.values.get("color_low", None)
    color_high_range = request.values.get("color_high", None)
    show_color = request.values.get("show_color", True)

    return color_low_range, color_high_range, show_color


def extract_flag_args_from_request():
    """ Gets minimum and maximum arguments from GET/POST params, returns None if the object is None or empty """
    all_flags_string = request.values.get("flags", "")
    all_flags_list = []
    # parse to create a dict of flags
    flags_seperated = all_flags_string.split('*')
    for flag in flags_seperated:
        if flag != "":
            flag_apart = flag.split(',')
            string = flag_apart[0].encode("utf-8")
            all_flags_list.append([string, int(flag_apart[1])])
    return all_flags_list


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
