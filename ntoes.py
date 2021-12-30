import datetime
import os
import re
import subprocess
import threading

import sublime
import sublime_plugin

# To open a file at a line number:
# window.open_file("{}:{}:{}".format(fname, row, col), sublime.ENCODED_POSITION)

MARKDOWN_SYNTAX = 'Packages/Markdown/Markdown.sublime-syntax'
# MARKDOWN_SYNTAX = 'Packages/MarkdownEditing/Markdown.sublime-syntax'

# Time in seconds between directory scans
SCAN_PERIOD = 10

# Time in seconds between Git syncs
SYNC_PERIOD = 60


class TodoList:
	def __init__(self):
		self.note_files = {}
		self.unload_requested = False
		self.processing_lock = threading.Lock()
		self.scan_event = threading.Event()
		self.sync_event = threading.Event()
		threading.Thread(target=self.scan_forever, daemon=True).start()
		threading.Thread(target=self.sync_forever, daemon=True).start()

	def on_unload(self):
		todo_list.unload_requested = True
		self.scan_event.set()
		self.sync_event.set()

	def get_base_dir(self):
		s = sublime.load_settings("Ntoes.sublime-settings")
		base_dir = s.get("base_dir", "~/ntoes/")
		base_dir = os.path.expanduser(base_dir)
		return base_dir

	def get_note_dir_from_title(self, title):
		note_date = datetime.datetime.strptime(title[:7], '%Y-%m')
		note_dir = self.get_base_dir()
		note_dir = os.path.join(note_dir, str(note_date.year))
		note_dir = os.path.join(note_dir, str(note_date.strftime('%m - %B')))
		return note_dir

	def get_todo_view(self):
		for window in sublime.windows():
			for view in window.views():
				if view.settings().get('is_todo') is not None:
					return view
		return None

	def update_todo_view(self):
		todo_view = self.get_todo_view()

		text = ''
		for file_path in sorted(self.note_files.keys(), reverse=True):
			fields = self.note_files[file_path]
			if len(fields['todos']):
				text += '# {}\n\n'.format(os.path.basename(file_path))
				for todo in fields['todos']:
					text += todo['text']
				text += '\n'

		todo_view.run_command('update_todo_view', {'text': text})
		# todo_view.run_command('move_to', {"extend": False, "to": "bol"})
		# todo_view.run_command('select_all')
		# todo_view.run_command('overwrite', {'characters': text})

	def scan_now(self):
		self.scan_event.set()

	def add_new_note_file(self, file_path):
		st = os.stat(file_path)
		self.note_files[file_path] = {
			"mtime": st.st_mtime,
			"todos": []
		}

	def scan_file(self, file_path):
		print('SCAN', file_path)
		
		todos = []
		with open(file_path, encoding='utf-8', errors='ignore') as file:
			for line_index, line in enumerate(file.readlines()):
				if '[ ]' in line:
					todos.append({'line': line_index, 'text': line})

		self.note_files[file_path]['todos'] = todos

	def scan_dir(self):
		base_dir = self.get_base_dir()
		note_paths = []

		# Stop tracking files that have been removed.
		removed_files = []
		for file_path in self.note_files.keys():
			if not os.path.exists(file_path):
				removed_files.append(file_path)
		for file_path in removed_files:
			del self.note_files[file_path]

		# Collect a list of files that exist.
		for dirpath, _, filenames in os.walk(base_dir):
			for file_name in filenames:
				if file_name.endswith('.md'):
					file_path = os.path.join(dirpath, file_name)
					note_paths.append(file_path)

		# Scan files that have been changed or are new.
		for file_path in sorted(note_paths, reverse=True):
			st = os.stat(file_path)

			if file_path in self.note_files:
				fields = self.note_files[file_path]
				if st.st_mtime <= fields["mtime"]:
					continue
				fields["mtime"] = st.st_mtime

			else:
				self.add_new_note_file(file_path)

			self.scan_file(file_path)
		
		self.update_todo_view()

	def scan_forever(self):
		while not self.unload_requested:
			if self.get_todo_view(): # Only scan if todo list is visible
				with self.processing_lock:
					self.scan_dir()
			self.scan_event.wait(SCAN_PERIOD)
			self.scan_event.clear()

	def sync_now(self):
		self.sync_event.set()

	def exec_git(self, cmd):
		git_cmd = 'git'
		cmd = [ git_cmd ] + cmd
		print(f'$ {" ".join(cmd)}')
		p = subprocess.run(cmd, text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		print(p.stdout)
		return p.stdout

	def sync_dir(self):
		base_dir = self.get_base_dir()
		os.chdir(base_dir)

		# Commit any uncommitted changes.
		status = self.exec_git(['status', '--porcelain'])
		if len(status) != 0:
			self.exec_git(['add', '.'])
			self.exec_git(['commit', '-m', 'detected changes'])

		# Fetch and merge any new changes (and resolve conflicts, leaving markers)
		self.exec_git(['fetch'])
		self.exec_git(['merge'])
		status = self.exec_git(['status', '--porcelain'])
		if len(status) != 0:
			self.exec_git(['add', '.'])
			self.exec_git(['commit', '-m', 'conflict markers'])

		# Submit any changes to the server.
		self.exec_git(['push'])

	def sync_forever(self):
		while not self.unload_requested:
			if self.get_todo_view(): # Only sync if todo list is visible
				with self.processing_lock:
					self.sync_dir()
			self.sync_event.wait(SYNC_PERIOD)
			self.sync_event.clear()


todo_list = TodoList()


class NewNoteCommand(sublime_plugin.WindowCommand):
	def run(self):
		self.window.show_input_panel("New Note", datetime.date.today().isoformat(), self.on_new_note, None, None)

	def on_new_note(self, title):		
		note_view = self.window.new_file()
		note_view.set_name(title + '.md')
		note_view.run_command('append', {'characters': '# {}\n\n'.format(title)})
		note_view.run_command('move_to', {'to': 'eof', 'extend': False})
		note_view.assign_syntax(MARKDOWN_SYNTAX)

		note_dir = todo_list.get_note_dir_from_title(title)
		os.makedirs(note_dir, 0o777, True)
		note_view.settings().set('default_dir', note_dir)
		note_view.settings().set('base_dir', todo_list.get_base_dir())

	def description(self):
		return "Creates a new note using the current date as a starting point."


class ShowNoteCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		todo_view = todo_list.get_todo_view()

		# Start with the current line.
		region = todo_view.sel()[0]
		todo_line = todo_view.line(region.a)
		todo_text = todo_view.substr(todo_line)
		# print(todo_line, todo_text)

		# Split the line into "[?] Blah blah..."
		line_re = re.compile(r'\[.\] (.*)')
		todo_m = line_re.match(todo_text)
		if not todo_m:
			print('Not a TODO line, no sync.')
			return
		todo_desc = todo_m.group(1)

		# Scan upwards for a heading like "# YYYY-MM-DD Title.md"
		file_heading_line, file_heading_text = todo_line, None
		while file_heading_line.a > 0:
			file_heading_line = todo_view.line(sublime.Region(file_heading_line.a - 1))
			file_heading_text = todo_view.substr(file_heading_line)
			if file_heading_text.startswith('# '):
				break
		if file_heading_text is None:
			print('No file header for this TODO.')
			return
		file_name = file_heading_text[2:]

		# Read the file, finding and updating the line in question.			
		note_dir = todo_list.get_note_dir_from_title(file_name)
		file_path = os.path.join(note_dir, file_name)
		# any_changes = False

		with open(file_path, encoding='utf-8', errors='ignore') as file:
			all_lines = file.readlines()
			
			for line_index, line in enumerate(all_lines):
				line_m = line_re.match(line)
				if line_m:
					line_desc = line_m.group(1)
					if line_desc == todo_desc:
						# print('found at', line_index, line_desc)
						new_line = todo_text + '\n'
						if all_lines[line_index] != new_line:
							all_lines[line_index] = new_line
							# any_changes = True
						break

		# # Write the file back with the modified line
		# if any_changes:
		# 	with open(file_path, 'w', encoding='utf-8') as file:
		# 		file.writelines(all_lines)

		# Navigate the window to the corresponding note.
		todo_view.window().open_file("{}:{}:{}".format(file_path, line_index + 1, 0), sublime.ENCODED_POSITION, 0)
		# sublime.run_command('move_to_group', {'group': 0})

	def description(self):
		return "In the TODO view, navigates to the corresponding note."


class MakeTodoCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		cursor_region = self.view.sel()[0]
		line_regions = self.view.lines(cursor_region)
		for region in reversed(line_regions):
			while True:
				if self.view.substr(region.begin()) not in [' ', '\t', '+', '-', '*', '#']:
					break
				if region.empty():
					break
				region.a += 1

			old_region = sublime.Region(region.begin(), region.begin() + 4)
			old_str = self.view.substr(old_region)
			if old_str == '[X] ':
				self.view.erase(edit, old_region)
			elif len(old_str) >= 4 and old_str[0] == '[' and old_str[2:4] == '] ':
				self.view.replace(edit, old_region, '[X] ')
			else:
				self.view.insert(edit, region.begin(), '[ ] ')

	def description(self):
		return "Toggles the selected lines todo state."


class UpdateTodoViewCommand(sublime_plugin.TextCommand):
	def run(self, edit, text):
		self.view.replace(edit, sublime.Region(8, self.view.size()), text)
		self.view.run_command('move_to', {"extend": False, "to": "bol"})


# Experiment with making changes in the todo view transfer to the file
# being edited: too noisy.

# class TodoViewEventListener(sublime_plugin.ViewEventListener):
# 	@classmethod
# 	def is_applicable(cls, settings):
# 		return settings.get('is_todo') is not None

# 	def on_modified(self):
# 		todo_list.sync_note_with_todo()


class NoteViewEventListener(sublime_plugin.ViewEventListener):
	def is_note_file(self):
		base_dir = os.path.normpath(todo_list.get_base_dir()) + os.path.sep
		file_name = os.path.normpath(self.view.file_name())

		return file_name.startswith(base_dir)

	def on_load(self):
		if not self.is_note_file():
			return

		# Setup completions for note file views.
		# https://www.sublimetext.com/docs/completions.html
		self.view.settings().set('auto_complete_triggers', [{
			'selector': 'text.html.markdown',
			'characters': '@#'
			}])
		self.view.settings().set('auto_complete', True)
		self.view.settings().set('auto_complete_use_index', True)
		self.view.settings().set('auto_complete_use_history ', True)
		


	def on_post_save_async(self):
		if not self.is_note_file():
			return

		todo_list.scan_now()

		with todo_list.processing_lock:
			status = todo_list.exec_git(['status', '--porcelain'])

			if len(status) != 0:
				todo_list.exec_git(['add', self.view.file_name()])
				todo_list.exec_git(['commit', '-m', self.view.file_name()])

			todo_list.sync_now()

	# def on_modified(self):
	# 	print("on_modified")

	# def on_text_changed(self):
	# 	print("on_text_changed")

	# 	if not self.is_note_file():
	# 		return

	# 	for change in changes:
	# 		if change.text == '@':
	# 			self.view.run_command('auto_complete', {
	# 				'disable_auto_insert': True,
	# 				'api_completions_only': True,
	# 				'next_competion_if_showing': True
	# 				})

	# def on_query_completions(self, prefix, locations):
	# 	if not self.is_note_file():
	# 		return

	# 	print("on_query_completions", prefix, locations)
	# 	if prefix.startswith('@'):
	# 		return [ "@jonlee" ]

	# 	if prefix.startswith('#'):
	# 		return [ "#DEI" ]

	# 	return None

	# 	# sel = view.sel()[0]
	# 	# regions = view.get_regions('smart_completions')
	# 	# for i,r in enumerate(regions):
	# 	#     if r.contains(sel):
	# 	#         if r == sel:
	# 	#             edit = view.begin_edit()
	# 	#             view.erase(edit, r)
	# 	#             view.end_edit(edit)
	# 	#         ac = RunSmartSnippetCommand.autocompletions.get(view.id())[i]
	# 	#         return [(x,x) for x in ac]

	# 	# l = []
	# 	# for s in SS.snip_files.keys():
	# 	#     if self.match_scope(view, SS.snip_files.get(s)):
	# 	#         t = (s[2:]+'\tSMART Snippet',s[2:])
	# 	#         l.append(t)
	# 	# return l


class ShowTodoCommand(sublime_plugin.WindowCommand):
	def run(self):
		todo_view = todo_list.get_todo_view()

		if todo_view is None:
			todo_view = self.window.new_file()
			todo_view.set_name('TODO')
			todo_view.set_scratch(True)
			todo_view.settings().set('gutter', False)
			todo_view.settings().set('is_todo', True)
			todo_view.assign_syntax(MARKDOWN_SYNTAX)
			todo_view.run_command('overwrite', {'characters': '# TODO\n\n'})
			todo_view.run_command('move_to', {"extend": False, "to": "bof"})

			self.window.run_command('new_pane')

		self.window.run_command('set_layout', {
			"cells": [[0, 0, 1, 1], [1, 0, 2, 1]], 
			"cols": [0.0, 0.7, 1.0], "rows": [0.0, 1.0]
			})

		todo_list.scan_now()

	def description(self):
		return "Show todo items from all notes in a new view."


class SetNotesDirCommand(sublime_plugin.WindowCommand):
	def run(self):
		self.window.show_input_panel('Notes Directory', "~/ntoes", self.on_set_notes_dir, None, None)

	def on_set_notes_dir(self, base_dir):
		base_dir = os.path.expanduser(base_dir)
		os.makedirs(base_dir, 0o777, True)

		s = sublime.load_settings("Ntoes.sublime-settings")
		s.set("base_dir", base_dir)

		sublime.save_settings("Ntoes.sublime-settings")

	def description(self):
		return "Selects the base directory for note files."


class SyncNotesCommand(sublime_plugin.WindowCommand):
	def run(self):
		todo_list.sync_now()

	def description(self):
		return "Synchronize notes with the remote server."


def plugin_unloaded():
	todo_list.on_unload()
