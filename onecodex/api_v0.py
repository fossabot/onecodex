"""
Functions to implement the v0 One Codex API calls.
"""
import json
import os
import requests
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
import sys
from threading import BoundedSemaphore, Thread
import urlparse
from onecodex import version


# Config
if os.environ.get("ONE_CODEX_API_BASE") is not None:
    BASE_API = os.environ.get("ONE_CODEX_API_BASE")
    print "ALL REQUESTS GOING THROUGH: %s" % BASE_API
else:
    BASE_API = "https://beta.onecodex.com/api/v0/"

BASE_URL = urlparse.urlparse(BASE_API)
BASE_URL = BASE_URL._replace(path='/').geturl()
DEFAULT_THREADS = 4


BAD_AUTH_MSG = ("\nYour login credentials appear be bad. Try logging out:"
                "\n    onecodex logout"
                "\n"
                "\nAnd then logging back in:"
                "\n    onecodex login"
                "\n")


# Helpers
def pprint(j, args):
    if args.pprint:
        print json.dumps(j, sort_keys=True,
                         indent=4, separators=(',', ': '))
    else:
        print j


def download_file_helper(url, input_path, auth=None):
    r = requests.get(url, stream=True, auth=auth)
    original_filename = urlparse.urlparse(r.url).path.split("/")[-1]
    if os.path.isdir(input_path):
        local_full_path = os.path.join(input_path, original_filename)
    else:
        local_full_path = input_path
    with open(local_full_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()
    print "Successfully downloaded %s to %s" % (original_filename, local_full_path)


class UploadCallback(object):
    def __init__(self, files):
        self.files = files
        self.filesizes = {f: float(os.path.getsize(f)) for f in files}
        self.filenames = {f: os.path.basename(f)[0:20] for f in files}
        self.progress = {f: 0.0 for f in files}
        self.last_bytes = {f: 0 for f in files}
        self.file_ns = {f: x for x, f in enumerate(files)}
        self.n = len(files)
        print "initializing upload callback", self.files

    def update(self, monitor, f):
        if self.last_bytes[f] != monitor.bytes_read:
            self.progress[f] = monitor.bytes_read / self.filesizes[f]
            self.last_bytes[f] = monitor.bytes_read
            self.update_progress()

    def _get_current_file(self):
        for ix, f in enumerate(self.files):
            if self.progress[f] >= 1:
                continue
            else:
                return ix + 1, f

    def update_progress(self):
        file_n, f = self._get_current_file()
        barLength = 20  # Modify this to change the length of the progress bar
        if self.progress[f] < 0:
            self.progress[f] = 0
            status = "Halt...\r\n"
        elif self.progress[f] >= 1:
            self.progress[f] = 1
            status = "Done.\r\n"
        else:
            status = ""
        block = int(round(barLength * self.progress[f]))
        text = "\r{0}: [{1}] {2:.2f}% {3} {4}".format(self.filenames[f],
                                                      "#" * block + "-" * (barLength - block),
                                                      self.progress[f] * 100, status, "%d/%d files" % (file_n, self.n))
        sys.stdout.write(text)
        sys.stdout.flush()


# Version checking function
def get_update_message():
    r = requests.post(BASE_API + "check_for_cli_update",
                      data={"version": version.VERSION,
                            "api_version": version.API_VERSION})
    if r.status_code == 200:
        j = r.json()
        if j.get("message"):
            print j["message"]


# Upload functions
def upload(args):
    """
    Note that this doesn't actually use the default API route -- it instead
    posts directly to S3.
    """
    creds = (args.credentials['api_key'], '')

    if args.threads:
        semaphore = BoundedSemaphore(args.max_threads)
        if args.max_threads != DEFAULT_THREADS:
            print "Uploading with up to %d threads." % args.max_threads

    # Get the initially needed routes
    r0 = requests.get(BASE_API + 'presign_upload', auth=creds)
    if r0.status_code == 401:
        print BAD_AUTH_MSG
        sys.exit(1)
    elif r0.status_code != 200:
        print "Failed to get upload signing credentials"
        sys.exit(1)

    j0 = r0.json()
    s3_url = j0['url']
    signing_url = BASE_URL.rstrip("/") + j0['signing_url']
    callback_url = BASE_URL.rstrip("/") + j0['callback_url']

    upload_threads = []
    upload_callback = UploadCallback(args.file)
    for f in args.file:
        if args.threads:  # parallel uploads
            # Multi-threaded uploads
            t = Thread(target=upload_helper,
                       args=(f, s3_url, signing_url, callback_url,
                             creds, upload_callback, semaphore))
            upload_threads.append(t)
            t.start()
        else:  # serial uploads
            upload_helper(f, s3_url, signing_url, callback_url, creds, upload_callback)

    if args.threads:
        for ut in upload_threads:
            ut.join()


def upload_helper(f, s3_url, signing_url, callback_url, creds,
                  upload_callback, semaphore=None):
    # First get the signing form data
    if semaphore is not None:
        semaphore.acquire()

    stripped_filename = os.path.basename(f)
    r1 = requests.post(signing_url, data={"filename": stripped_filename, "via_api": "true"},
                       auth=creds)
    if r1.status_code != 200:
        print "Failed to get upload signing credentials"
        sys.exit(1)

    # Coerce to str or MultipartEncoder fails
    # Need a list to preserve order for S3
    fields = []
    for k, v in r1.json().items():
        fields.append((str(k), str(v)))

    fields.append(("file", (stripped_filename, open(f, mode='rb'), "text/plain")))
    e = MultipartEncoder(fields)
    m = MultipartEncoderMonitor(e, lambda x: upload_callback.update(x, f))
    r2 = requests.post(s3_url, data=m, headers={"Content-Type": m.content_type})
    if r2.status_code != 201:
        print "Upload failed. Please contact help@onecodex.com for assistance."
        sys.exit(1)

    # Finally, issue a callback
    r3 = requests.post(callback_url, auth=creds, data={
        "location": r2.headers['location'],
        "size": os.path.getsize(f)
    })
    if r3.status_code == 200:
        # print "Successfully uploaded: %s" % f
        pass
    else:
        print "Failed to upload: %s" % f
        sys.exit(1)

    if semaphore is not None:
        semaphore.release()


# Helper for /route/UUID pattern
def api_helper(args, route, supplement=""):
    creds = (args.credentials['api_key'], '')
    if not getattr(args, route):
        r = requests.get(BASE_API + route + supplement,
                         auth=creds)
        j = r.json()
        pprint(j, args)
    else:
        for uuid in getattr(args, route):
            r = requests.get(BASE_API + route + "/" + uuid + supplement,
                             auth=creds)
            j = r.json()
            pprint(j, args)

    if r.status_code == 401:
        print BAD_AUTH_MSG
        sys.exit(1)


def samples(args):
    api_helper(args, route="samples")


def analyses(args):
    if not args.raw and not args.table:
        api_helper(args, route="analyses")
    elif args.raw and args.table:
        print "Can only request raw or table data at the same time."
        sys.exit(1)
    elif args.raw and not args.table:
        if len(args.analyses) != 1:
            print "Can only request raw data on one Analysis at a time."
            sys.exit(1)
        download_file_helper(BASE_API + "analyses/" + args.analyses[0] + "/raw",
                             input_path=args.raw,
                             auth=(args.credentials['api_key'], ''))
    elif args.table and not args.raw:
        if len(args.analyses) != 1:
            print "Can only request table data on one Analysis at a time."
            sys.exit(1)
        api_helper(args, route="analyses", supplement="/table")


def references(args):
    api_helper(args, route="references")