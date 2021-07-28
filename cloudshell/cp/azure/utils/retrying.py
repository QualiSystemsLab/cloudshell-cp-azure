import traceback

from msrest.exceptions import ClientRequestError
from msrestazure.azure_exceptions import CloudError
from requests.packages.urllib3.exceptions import ConnectionError

RETRYABLE_ERROR_STRING = "retryable"
RETRYABLE_WAIT_TIME = 2000
RETRYABLE_ERROR_MAX_ATTEMPTS = 20
VM_DISK_DETACH_MAX_ATTEMPT_NUMBER = 300


def retry_on_connection_error(exception):
    """Return True if we got IO error and should retry an API call.

    :param Exception exception:
    """
    return any(
        [
            isinstance(exception, ClientRequestError),
            isinstance(exception, ConnectionError),
            _is_pool_closed_error(),
        ]
    )


def _is_pool_closed_error():
    return "pool is closed" in traceback.format_exc()


def retry_on_retryable_error(exception: Exception):
    """Return True if we got retryable error and should retry an API call."""
    return (
        isinstance(exception, CloudError)
        and RETRYABLE_ERROR_STRING in exception.message.lower()
    )


def retry_on_vm_disk_detach_error(exception: Exception):
    """Return True if we got an error that disk is still attached to the VM."""
    return (
        isinstance(exception, CloudError)
        and "is being attached to vm" in exception.message.lower()
    )
