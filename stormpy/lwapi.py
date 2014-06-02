"""python-stormondemand - a simple client library for accessing the Liquid Web Storm API, written in python

	see the official documentation for more information about the api itself:
		http://www.liquidweb.com/StormServers/api/docs/v1

	 Copyright 2013 Liquid Web, Inc. 

	 Licensed under the Apache License, Version 2.0 (the "License");
	 you may not use this file except in compliance with the License.
	 You may obtain a copy of the License at

		 http://www.apache.org/licenses/LICENSE-2.0

	 Unless required by applicable law or agreed to in writing, software
	 distributed under the License is distributed on an "AS IS" BASIS,
	 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
	 See the License for the specific language governing permissions and
	 limitations under the License.
"""

import os
import requests
import time
import json
from getpass import getpass

class HTTPException(Exception):
"""
	raised when an HTTP error is encountered; e.g. 401 Permission Denied. If StormOnDemand itself has an issue preventing the request, a StormException may be raised.
"""
	def __init__(self, code, text):
		self.code = code
		self.text = text
		message = ('Received bad response from the server: %d\n%s' % (code, text))
		super(BadResponseException, self).__init__(message)

class StormException(Exception):
"""
error_class - the type of error encountered, follows the form `LW::Exception::Something::Bad`; you can read more about possible error types here: https://www.stormondemand.com/api/docs/tutorials/exceptions.html
error_message - details of the error recieved

full_message - the full text of the error provided by the server. Will be used as the message of the python base Exception type. 

this exception will be raised when there is an error_class key in the server response. If you would like to handle such errors yourself, this exception may be disabled by setting `raise_exceptions=False` when creating an LWApi object. Regardless, the BadResponseException will still be raised if the server responds in a way that can't be handled. e.g. 401 Permission Denied.
"""
	def __init__(self, error_class, error_message, full_message):
		self.error_class = error_class
		self.error_message = error_message
		super(StormException, self).__init__(full_message)

class LWApi(object):
	def __init__(self, user, password=None, url='api.stormondemand.com', api_version='v1', verify=True, authfile=None, raw_json=False, raise_exceptions=True):
		"""
user - the api user (a string)

password - the user's password (a string). If the password is omitted, it will need to be entered via stdin anytime the auth token needs to be updated. This is only recommended for CLI applications. If CLI interactivity is not required, the password should be supplied.

url - the url of the storm on demand api. This is for testing and development purposes, and won't need to be changed for normal usage. 

api_version - the version of the api that will be used (a string). defaults to 'v1'. 'bleed' may also be used at the moment to access the API's neweset methods. 

verify - whether the SSL certificate for the api should be verified (a bool). Defaults to True. This is primarily for testing. The public api should *always* have a valid SSL certificate!

authfile - by default, auth tokens are not stored persistently, and will only exist until the LWApi object is garbage collected. if a filename is supplied, LWApi will attempt to store the auth token (along with its expiry time) there so that it may be used by multiple LWApi objects. This behavior may be desriable for certain CLI applications where a new LWApi object is created for each request.

raw_json - by default, LWApi.req() will return a python object generated from the json string sent by the server. By setting this value to True, req() will return the raw json string. This may also be overridden while calling the method if desired.

raise_exceptions - by default, LWApi will raise a StormException if there is an error_class key in the server's response. If you would like to handle these errors yourself. this can be set to False. you can read more about Error Responses here: https://www.stormondemand.com/api/docs/tutorials/exceptions.html ; please note that bad http responses (e.g. 401) will still cause a HTTPException to be raised.
		"""
		self._url = 'https://%s/%s/' % (url, api_version) 
		self._user = user
		self._password = password

		self._verify = verify
		self._raw_json = raw_json
		self._raise_exceptions = raise_exceptions

		self._authfile = authfile

		# auth token & expiry time. These will be set via calls to _get_token().
		self._token = ''
		self._expires = 0

	def _get_token(self):
		"""
			obtain an auth token, either via the /Account/Auth/token api method, or by reading a locally stored token.
		"""
		# if no password is given
		if self._password == None:
		
			# check to see if we're using an auth file.
			if self._authfile:
				# if we are, try to use it.
				try:
					# read the values in
					af = open(self._authfile, 'r')
					self._token = af.readline()
					self._expires = int(af.readline())
					af.close()

					# make sure the token we read is still good
					now = int(time.time())
					if self._expires == 0 or now > self._expires + 5:
						# it's sort of shady to raise IOError when there's no IOError
						# but it's an easy way to get us somewhere that will skip over
						# the early return AND get us the password 
						raise IOError

					# if the file was readable and had a valid token
					# then exit from the function early
					return
					
				
				# if it's not there, grab the password as normal, we'll write the authfile later
				except IOError:
					print "need to retrieve auth token. please enter password for user `%s`" % self._user
					passwd = getpass('pass > ')

			# if no auth file was given, grab the password as normal.
			else:
				print "need to retrieve auth token. please enter password for user `%s`" % self._user
				passwd = getpass('pass > ')
		else:
			passwd = self._password

		# assemble and send the post request to obtain the key
		auth = requests.auth.HTTPBasicAuth(self._user, passwd)
		url = self._url + 'Account/Auth/token'
		data = '{"params":{"timeout":"3600"}}'
		r = requests.post(url=url, auth=auth, data=data, verify=self._verify)

		# raise an error if we don't get a 200 response
		if r.status_code != 200:
			raise BadResponseException(r.status_code, r.text)

		else:
			self._token = json.loads(r.text)['token']
			self._expires = int(json.loads(r.text)['expires'])

			# if the user would like to save the token, write it into the file with
			# the expiry time.
			if self._authfile:
				af = open(authfile, 'w')
				af.write('%s\n%d' % (self._token, self._expires))
				af.close

	def _get_auth(self):
		"""
			returns a requests.auth.HTTPBasicAuth object
		"""
		now = int(time.time())
		# if the auth token is not set, or if it has expired/is about to expire
		if self._expires == 0 or now > self._expires + 5:
			self._get_token()

		return requests.auth.HTTPBasicAuth(self._user, self._token)
			

	def req(self, path, data={}, raw_json=None):
		"""make a POST request to the storm api
			path -- a string contaning the method you'd like to call. Methods are Case sensitive. Leading slash may be included or omitted
				ex. 'Utilities/Info/ping'
			
			data -- POST data to be used by the request, formatted as a dict. parameters be added directly:
				data = {'page_size':'20'}
			or as the value to a 'params' key:
				data = {"params":{"page_size":"20"}}

			The latter is how the API expects the data to be formatted, but if a dict of parameters is passed directly, LWApi will add the params key automatically. This should be a little easier to work with.

			raw_json -- may be used to override the default return value. True to return a json string, False to return an object, None to use the instance default. 

			RETURNS: either a json formatted string, or the python object composed from said string, dependign on user's preference. 
		"""
		# if the path starts with a /, strip it off.
		if path[0] == '/':
			path = path[1:]

		# if the postdata is enclosed in a 'params' hash, just use the value.
		# support the {"params":{"key":"value"}} because it complies with the
		# docs, but the data is easier to use without it, so we'll put it in
		# when we make the request.
		if data.keys() == ['params']:
			data = data['params']


		# this is where input validation should take place
		# presently, we just make sure that the required parameters are given
		# but eventually we will add type checking

		url = self._url + path
		req = requests.post(url=url, auth=self._get_auth(),\
												data=json.dumps({'params':data}), verify=self._verify)

		# make sure the request was completed successfully
		if req.status_code != 200:
			raise BadResponseException(req.status_code, req.text)

		# turn the response into a json object
		response = json.loads(req.text)

		# handling errors: per the API docs, check the response for an 'error_class' key:
		if 'error_class' in response:
			raise StormException(response['error_class'], response['error_message'], response['full_message']) 

		# no error:
		# if the user has not overriden the return setting for this call, return the default type
		if raw_json is None:
			if self._raw_json:
				return req.text
			else:
				return response

		elif raw_json:
			return req.text
		else:
			return response
