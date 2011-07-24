# -*- coding: utf-8 -*-
# Copyright (c) 2011, Per Rovegård <per@rovegard.se>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the authors nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import urllib2
import re
import aplog as log
from upnp import SoapMessage, SoapError

__all__ = [
    'fetch_url',
    'send_soap_message',
    'hms_to_sec',
    'sec_to_hms',
    'split_usn',
    'get_max_age',
]


def fetch_url(url):
    """
    Download data from the specified URL, and return a file-like object.
    
    Wrapper around urllib2.urlopen with no additional logic but logging.
    Any error raised by urllib2.urlopen is re-raised by this function.

    """
    req = urllib2.Request(url)

    log.msg(2, 'Fetching URL %s' % (url, ))
    try:
        handle = urllib2.urlopen(req)
    except urllib2.URLError, err:
        log.err(err, 'Failed to fetch URL %s' % (url, ))
        raise err

    return handle


class MPOSTRequest(urllib2.Request):

    """
    Internal Request sub class used by send_soap_message.
    
    The HTTP method is set to 'M-POST' unconditionally (i.e., regardless
    of the presence of data to post).

    """

    def __init__(self, url, data=None, headers={}):
        urllib2.Request.__init__(self, url, data, headers)

    def get_method(self):
        return "M-POST"


def send_soap_message(url, msg, mpost=False):
    """
    Send a SOAP message to the given URL.
    
    The HTTP headers mandated by the UPnP specification are added. Also, if
    posting fails with a 405 error, another attempt is made with slightly
    different headers and method set to M-POST.

    Return a SoapMessage or a SoapError, depending on the outcome of the call.

    Raise a urllib2.URLError or a urllib2.HTTPError if something goes wrong.

    """
    req = MPOSTRequest(url) if mpost else urllib2.Request(url)

    # add headers to the request
    req.add_header('CONTENT-TYPE', 'text/xml; charset="utf-8"')
    req.add_header('USER-AGENT', 'OS/1.0 UPnP/1.0 airpnp/1.0')
    if mpost:
        req.add_header('MAN',
                       '"http://schemas.xmlsoap.org/soap/envelope/"; ns=01')
        req.add_header('01-SOAPACTION', msg.get_header())
    else:
        req.add_header('SOAPACTION', msg.get_header())

    # add the SOAP message as data
    req.add_data(msg.tostring().encode("utf-8"))

    try:
        handle = urllib2.urlopen(req)
        response = SoapMessage.parse(handle)
    except urllib2.HTTPError, err:
        if err.code == 405 and not mpost:
            log.msg(2, 'Got 405 response in response to SOAP message, trying' +
                    'the M-POST way')
            return send_soap_message(url, msg, True)
        elif err.code == 500:
            # SOAP error
            response = SoapError.parse(err.read())
        else:
            log.err(err, 'Failed to send SOAP message')
            raise err
    except urllib2.URLError, err:
        log.err(err, "Failed to send SOAP message")
        raise err

    return response


def hms_to_sec(hms):
    """
    Convert a HMS time string to seconds.

    The supported HMS time string formats are:
        
    H+:MM:SS[.F+] or H+:MM:SS[.F0/F1]

    where:
        * H+ means one or more digits to indicate elapsed hours
        * MM means exactly 2 digits to indicate minutes (00 to 59)
        * SS means exactly 2 digits to indicate seconds (00 to 59)
        * [.F+] means optionally a dot followed by one or more digits to
          indicate fractions of seconds
        * [.F0/F1] means optionally a dot followed by a fraction, with F0
          and F1 at least one digit long, and F0 < F1

    The string may be preceded by an optional + or - sign, and the decimal
    point itself may be omitted if there are no fractional second digits.

    A ValueError is raised if the input string does not adhere to the
    requirements stated above.

    """
    hours, minutes, seconds = hms.split(':')
    if len(minutes) != 2 or len(seconds.split('.')[0]) != 2:
        raise ValueError('Minute and second parts must have two digits each.')
    hours = int(hours)
    minutes = int(minutes)
    if minutes < 0 or minutes > 59:
        raise ValueError('Minute out of range, must be 00-59.')
    if seconds.find('/') > 0:
        whole, frac = seconds.split('.')
        sf0, sf1 = frac.split('/')
        sf0 = int(sf0)
        sf1 = int(sf1)
        if sf0 >= sf1:
            raise ValueError(
                'Nominator must be less than denominator in exact fraction.')
        seconds = int(whole) + float(sf0) / sf1
    else:
        seconds = float(seconds)
    if seconds < 0 or seconds >= 60.0:
        raise ValueError('Second out of range, must be 00-60 (exclusive).')
    sec = 3600.0 * abs(hours) + 60.0 * minutes + seconds
    return sec if hours >= 0 else -sec


def sec_to_hms(sec):
    """
    Convert a number of seconds to an HMS time string.
    
    The resulting string has the form:

    H+:MM:SS[.F+]

    This function is the inverse of the hms_to_sec function. If the
    number of seconds is negative, the resulting string will have a
    preceding - sign. It will never have a preceding + sign, nor will
    the fraction be expressed as an integer division of the form F0/F1.

    """
    sgn = -1 if sec < 0 else 1
    sec = abs(sec)
    frac = sec - int(sec)
    sec = int(sec)
    seconds = sec % 60
    mins = (sec - seconds) / 60
    minutes = mins % 60
    hours = (mins - minutes) / 60
    hms = '%d:%02d:%02d' % (hours, minutes, seconds)
    if frac > 0:
        hms = '%s%s' % (hms, str(frac)[1:])
    return '-%s' % (hms, ) if sgn < 0 else hms


def split_usn(usn):
    """Split a USN into a UDN and a device or service type.
    
    USN is short for Unique Service Name, and UDN is short for Unique Device
    Name.  If the USN only contains a UDN, the type is empty.

    Return a list of exactly two items.

    """
    parts = usn.split('::')
    if len(parts) == 2:
        return parts
    else:
        return [parts[0], '']


def get_max_age(headers):
    """Parse the 'max-age' directive from the 'CACHE-CONTROL' header.
    
    Arguments:
    headers -- dictionary of HTTP headers

    Return the parsed value as an integer, or None if the 'max-age' directive
    or the 'CACHE-CONTROL' header couldn't be found, or if the header is
    invalid in any way.

    """
    ret = None
    cache_control = headers.get('CACHE-CONTROL')
    if not cache_control is None:
        parts = re.split(r'\s*=\s*', cache_control)
        if len(parts) == 2 and parts[0] == 'max-age' and re.match(r'^\d+$',
                                                                  parts[1]):
            ret = int(parts[1])
    return ret
