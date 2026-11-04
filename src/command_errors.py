"""Stable broad CLI categories; no string-matching of user paths to infer errors."""
import sqlite3
import subprocess


def describe(error,*,canceled=False):
    if canceled:code='CANCELED'
    elif isinstance(error,BlockingIOError):code='BUSY'
    elif isinstance(error,(TimeoutError,subprocess.TimeoutExpired)):code='TIMEOUT'
    elif isinstance(error,FileNotFoundError):code='ASSET_MISSING'
    elif isinstance(error,PermissionError):code='ACCESS_DENIED'
    elif isinstance(error,sqlite3.Error):code='CATALOG_ERROR'
    elif isinstance(error,subprocess.SubprocessError):code='WORKER_FAILED'
    elif isinstance(error,(ValueError,TypeError,KeyError)):code='INVALID_REQUEST_OR_STATE'
    else:code='LOCAL_IO_ERROR'
    return {'code':code,'message':str(error)[:4000],
            'recovery':'Inspect jobs.status with the original request ID before resubmitting an admitted render. Never assume a timeout/cancel means nothing was published.'}
