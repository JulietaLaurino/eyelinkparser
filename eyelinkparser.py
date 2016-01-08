# -*- coding: utf-8 -*-

"""
This file is part of eyelinkparser.

eyelinkparser is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

eyelinkparser is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with datamatrix.  If not, see <http://www.gnu.org/licenses/>.
"""


import sys
import shlex
import os
from datamatrix import DataMatrix, SeriesColumn, cached
from datamatrix.py3compat import *
import numpy as np

class EyeLinkParser(object):

	def __init__(self, folder=u'data', ext=u'.asc'):

		self.dm = DataMatrix()
		for fname in os.listdir(folder):
			if not fname.endswith(ext):
				continue
			path = os.path.join(folder, fname)
			self.dm <<= self.parse_file(path)

	# Helper functions that can be overridden

	def on_start_file(self):

		pass

	def on_end_file(self):

		pass

	def on_start_trial(self):

		pass

	def on_end_trial(self):

		pass

	def parse_line(self, l):

		pass

	# Internal functions

	def print_(self, s):

		sys.stdout.write(s)
		sys.stdout.flush()

	def parse_file(self, path):

		self.filedm = DataMatrix()
		self.filedm.source = os.path.splitext(os.path.basename(path))[0]
		self.print_(u'Parsing %s ' % path)
		self.path = path
		self.on_start_file()
		ntrial = 0
		with open(path) as f:
			for line in f:
				l = self.split(line)
				if self.is_start_trial(l):
					ntrial += 1
					self.print_(u'.')
					self.filedm <<= self.parse_trial(f)
		self.on_end_file()
		self.print_(u' (%d trials)\n' % ntrial)
		return self.filedm

	def parse_trial(self, f):

		self.trialdm = DataMatrix(length=1)
		self.trialdm.path = self.path
		self.trialdm.trialid = self.trialid
		self.on_start_trial()
		for line in f:
			l = self.split(line)
			if self.is_end_trial(l):
				break
			self.parse_variable(l)
			self.parse_phase(l)
			self.parse_line(l)
		self.on_end_trial()
		return self.trialdm

	def parse_variable(self, l):

		# MSG	6740629 var rt 805
		if len(l) == 5 and l[0] == u'MSG' and l[2] == u'var':
			self.trialdm[l[3]] = l[4]

	def parse_phase(self, l):

		# MSG	[timestamp] start_phase [name]
		if len(l) == 4 and l[0] == u'MSG' and l[2] == u'start_phase':
			assert(self.current_phase is None)
			assert(self.current_phase not in self.trialdm)
			self.current_phase = l[3]
			self.ptrace = []
			self.xtrace = []
			self.ytrace = []
			return
		# MSG	[timestamp] end_phase [name]
		if len(l) == 4 and l[0] == u'MSG' and l[2] == u'end_phase':
			assert(self.current_phase == l[3])
			for prefix, trace in [
				(u'ptrace_', self.ptrace),
				(u'xtrace_', self.xtrace),
				(u'ytrace_', self.ytrace),
				]:
					colname = prefix + self.current_phase
					self.trialdm[colname] = SeriesColumn(len(trace))
					self.trialdm[colname][0] = trace
			self.current_phase = None
			return
		if self.current_phase is None:
			return
		s = self.to_sample(l)
		if s is None:
			return
		self.ptrace.append(s['pupil_size'])
		self.xtrace.append(s['x'])
		self.ytrace.append(s['y'])

	def is_start_trial(self, l):

		# MSG	6735155 start_trial 1
		if len(l) == 4 and l[0] == u'MSG' and l[2] == u'start_trial':
			self.trialid = l[3]
			self.current_phase = None
			return True
		return False

	def is_end_trial(self, l):

		# MSG	6740629 end_trial
		if len(l) == 3 and l[0] == u'MSG' and l[2] == u'end_trial':
			self.trialid = None
			return True
		return False

	def split(self, line):

		l = []
		for s in shlex.split(line):
			try:
				l.append(int(s))
			except:
				try:
					l.append(float(s))
				except:
					l.append(s)
		return l

	def to_saccade(self, l):

		"""
		desc:
			Attempts to parse a line (in list format) into a dictionary of
			saccade information.

		TODO:
		Handle other fixation formats

		Arguments:
		l -- a list

		Returns:
		None if the list isn't a saccade, otherwise a dictionary with the
		following keys: 'sx', 'sy', 'ex', 'ey', 'sTime', 'eTime', 'duration',
		'size'.
		"""

		if len(l) < 11 or l[0] != "ESACC":
			return None

		try:
			saccade = {}
			if len(l) == 15:
				saccade["sx"] = l[9]
				saccade["sy"] = l[10]
				saccade["ex"] = l[11]
				saccade["ey"] = l[12]
			else:
				saccade["sx"] = l[5]
				saccade["sy"] = l[6]
				saccade["ex"] = l[7]
				saccade["ey"] = l[8]
			saccade["size"] = np.sqrt( (saccade['sx']-saccade['ex'])**2 +
				(saccade['sy']-saccade['ey'])**2)
			saccade["sTime"] = l[2]
			saccade["eTime"] = l[3]
			saccade["duration"] = saccade["eTime"] - saccade["sTime"]
			return saccade
		except:
			return None

	def to_sample(self, l):

		"""
		desc:
			Attempts to parse a line (in list format) into a dictionary of
			sample information. Samples with missing data are not matched.
			The expected format is:

				# Timestamp x y pupil size ...
				4815155   168.2   406.5  2141.0 ...

			or (during blinks):

				661781	   .	   .	    0.0	...

			or (elaborate format):

				548367    514.0   354.5  1340.0 ...      -619.0  -161.0    88.9 ...CFT..R.BLR

		Arguments:
		l -- a list

		Returns:
		None if the list isn't a sample, otherwise a dictionary with the
		following keys: 'x', 'y', 'time'.
		"""

		if len(l) not in (5, 9) or isinstance(l[0], basestring):
			return
		sample = {}
		sample["time"] = l[0]
		if isinstance(l[0], basestring):
			return
		sample["x"] = l[1]
		if isinstance(l[1], basestring):
			return
		sample["y"] = l[2]
		if l[3] == 0 or isinstance(l[3], basestring):
			return
		sample['pupil_size'] = l[3]
		return sample

	def to_fixation(self, l):

		"""
		desc:
			Attempts to parse a line (in list format) into a dictionary of fixation
		information.

		TODO:
		Handle other fixation formats

		Arguments:
		l -- a list

		Returns:
		None if the list isn't a fixation, otherwise a dictionary with the
		following keys: 'x', 'y', 'sTime', 'eTime', 'duration'.
		"""

		if len(l) != 8 or l[0] != "EFIX":
			return None
		fixation = {}
		# EFIX R   1651574	1654007	2434	  653.3	  557.8	   4710
		fixation["x"] = l[5]
		fixation["y"] = l[6]
		fixation['pupilSize'] = l[7]
		fixation["sTime"] = l[2]
		fixation["eTime"] = l[3]
		fixation["duration"] = fixation['eTime'] - fixation['sTime']
		return fixation

@cached
def parse(parser=EyeLinkParser, **kwdict):

	return parser(**kwdict).dm
