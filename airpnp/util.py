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
from cStringIO import StringIO
from twisted.web import client, error, http

__all__ = [
    'send_soap_message',
    'send_soap_message_deferred',
    'split_usn',
    'get_max_age',
]


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


def send_soap_message_deferred(url, msg, mpost=False, deferred=None):
    """
    Send a SOAP message to the given URL.
    
    The HTTP headers mandated by the UPnP specification are added. Also, if
    posting fails with a 405 error, another attempt is made with slightly
    different headers and method set to M-POST.

    Return a Deferred, whose callback will be called with a SoapMessage or a
    SoapError, depending on the outcome.

    """
    def handle_error(fail):
        if fail.check(error.Error):
            err = fail.value
            status = int(err.status)
            if not mpost and status == http.NOT_ALLOWED:
                # new attempt
                # don't pass the deferred here, because we're already
                # within the callback/errback chain
                return send_soap_message_deferred(url, msg, mpost=True)
            elif status == http.INTERNAL_SERVER_ERROR:
                # return to the callback chain
                return SoapError.parse(err.response)
        log.err(fail, "Failed to send SOAP message to %s" % (url, ))
        fail.raiseException()

    # setup request headers
    headers = {}
    headers['Content-Type'] = 'text/xml; charset="utf-8"'
    if mpost:
        headers['Man'] = '"http://schemas.xmlsoap.org/soap/envelope/"; ns=01'
        headers['01-Soapaction'] = msg.get_header()
    else:
        headers['Soapaction'] = msg.get_header()

    # prepare the post data
    data = msg.tostring().encode("utf-8")

    # select method
    method = 'POST' if not mpost else 'M-POST'

    # initiate the request and add initial handlers
    if deferred:
        def tourl(value):
            return url
        # the deferred is an initiator, so we don't care about
        # its result
        d = deferred
        d.addCallback(tourl)
        d.addCallback(client.getPage, method=method, headers=headers,
                      postdata=data, agent='OS/1.0 UPnP/1.0 airpnp/1.0')
    else:
        d = client.getPage(url, method=method, headers=headers, postdata=data,
                           agent='OS/1.0 UPnP/1.0 airpnp/1.0')
    d.addCallback(StringIO)
    d.addCallback(SoapMessage.parse)
    d.addErrback(handle_error)
    return d


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
    if cache_control:
        parts = re.split(r'\s*=\s*', cache_control)
        if len(parts) == 2 and parts[0] == 'max-age' and re.match(r'^\d+$',
                                                                  parts[1]):
            ret = int(parts[1])
    return ret
