import datetime
import os
<<<<<<< HEAD
import re
=======
import subprocess
>>>>>>> 8f60fd7 (sync wip)
import threading
import time

import sublime
import sublime_plugin

# To open a file at a line number:
# window.open_file("{}:{}:{}".format(fname, row, col), sublime.ENCODED_POSITION)

MARKDOWN_SYNTAX = 'Packages/Markdown/Markdown.sublime-syntax'
# MARKDOWN_SYNTAX = 'Packages/MarkdownEditing/Markdown.sublime-syntax'

SCAN_PERIOD = 10


class NewNoteCommand(sublime_plugin.WindowCommand):
	def run(self):
		self.window.show_input_panel("New Note", datetime.date.today().isoformat(), self.on_new_note, None, None)

	def on_new_note(self, title):		
		note_view = self.window.new_file()
		note_view.set_name(title + '.md')
		note_view.run_command('append', {'characters': '# {}\n\n'.format(title)})
		note_view.run_command('move_to', {'to': 'eof', 'extend': False})
<<<<<<< HEAD
		note_view.assign_syntax('Packages/Markdown/Markdown.sublime-syntax')
=======
		note_view.assign_syntax(MARKDOWN_SYNTAX)
>>>>>>> 8f60fd7 (sync wip)

		s = sublime.load_settings("Ntoes.sublime-settings")

		note_date = datetime.datetime.strptime(title[:7], '%Y-%m')

		base_dir = s.get("base_dir", "~/ntoes/")
		base_dir = os.path.expanduser(base_dir)
		base_dir = os.path.join(base_dir, str(note_date.year))
		base_dir = os.path.join(base_dir, str(note_date.strftime('%m - %B')))

		os.makedirs(base_dir, 0o777, True)

		note_view.settings().set('default_dir', base_dir)
		note_view.settings().set('base_dir', s.get("base_dir", "~/ntoes/"))


class ShowNoteCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		s = self.view.settings()

		for region in self.view.sel():
			todo_line = self.view.line(region.a)
			todo_text = self.view.substr(todo_line)
			print(todo_line, todo_text)

			line_re = re.compile(r'\[.\] (.*)')
			todo_m = line_re.match(todo_text)
			if not todo_m:
				print('Not a TODO line, no sync.')
				return
			todo_desc = todo_m.group(1)

			file_heading_line, file_heading_text = todo_line, None
			while file_heading_line.a > 0:
				file_heading_line = self.view.line(sublime.Region(file_heading_line.a - 1))
				file_heading_text = self.view.substr(file_heading_line)
				if file_heading_text.startswith('# '):
					break
			if file_heading_text is None:
				print('No file header for this TODO.')
				return
			file_name = file_heading_text[2:]

			note_date = datetime.datetime.strptime(file_name[:7], '%Y-%m')
			base_dir = s.get("todo_base_dir")
			base_dir = os.path.expanduser(base_dir)
			base_dir = os.path.join(base_dir, str(note_date.year))
			base_dir = os.path.join(base_dir, str(note_date.strftime('%m - %B')))

			file_path = os.path.join(base_dir, file_name)
			# print(file_heading_line, file_heading_text, file_name, file_path)
			
			with open(file_path) as file:
				all_lines = file.readlines()
				
				for line_index, line in enumerate(all_lines):
					line_m = line_re.match(line)
					if line_m:
						line_desc = line_m.group(1)
						if line_desc == todo_desc:
							print('found at', line_index, line_desc)
							all_lines[line_index] = todo_text + '\n'
							break

			self.view.window().open_file("{}:{}:{}".format(file_path, line_index + 1, 0), sublime.ENCODED_POSITION, 0)
			# sublime.run_command('move_to_group', {'group': 0})


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
		return "Toggles the current line's TODO item status."


class UpdateTodoViewCommand(sublime_plugin.TextCommand):
	def run(self, edit, text):
		self.view.replace(edit, sublime.Region(8, self.view.size()), text)
		self.view.run_command('move_to', {"extend": False, "to": "bol"})


class TodoList:
	def __init__(self):
		self.note_files = {}
		self.todo_view = None
		self.scan_thread = None
		self.cancel_scanning = False
		self.wakeup_event = threading.Event()

	def start_scanning(self):
		if self.scan_thread is None:
			self.scan_thread = threading.Thread(target=self.scan_forever, daemon=True)
			self.scan_thread.start()

	def stop_scanning(self):
		self.cancel_scanning = True

	def is_scanning(self):
		return self.scan_thread is not None

	def add_note_file(self, file_path):
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

	def update_view(self):
		if self.todo_view is None:
			return

		text = ''
		for file_path in sorted(self.note_files.keys(), reverse=True):
			fields = self.note_files[file_path]
			if len(fields['todos']):
				text += '# {}\n\n'.format(os.path.basename(file_path))
				for todo in fields['todos']:
					text += todo['text']
				text += '\n'

		self.todo_view.run_command('update_todo_view', {'text': text})
		# self.todo_view.run_command('move_to', {"extend": False, "to": "bol"})
		# self.todo_view.run_command('select_all')
		# self.todo_view.run_command('overwrite', {'characters': text})

	def scan_dir(self):
		print('SCAN_DIR')
		s = sublime.load_settings("Ntoes.sublime-settings")
		base_dir = s.get("base_dir", "~/ntoes/")
		base_dir = os.path.expanduser(base_dir)

		note_paths = []

		for dirpath, _, filenames in os.walk(base_dir):
			for file_name in filenames:
				if file_name.endswith('.md'):
					file_path = os.path.join(dirpath, file_name)
					note_paths.append(file_path)
<<<<<<< HEAD
			
=======

		for file_path in sorted(note_paths, reverse=True):
			st = os.stat(file_path)

			if file_path in self.note_files:
				fields = self.note_files[file_path]
				if st.st_mtime <= fields["mtime"]:
					continue
				fields["mtime"] = st.st_mtime

			else:
				self.add_note_file(file_path)

			self.scan_file(file_path)
			self.update_view()

	def sync_dir(self):
		print('SYNC_DIR')
		s = sublime.load_settings("Ntoes.sublime-settings")
		base_dir = s.get("base_dir", "~/ntoes/")
		base_dir = os.path.expanduser(base_dir)

		note_paths = []

		for dirpath, _, filenames in os.walk(base_dir):
			for file_name in filenames:
				if file_name.endswith('.md'):
					file_path = os.path.join(dirpath, file_name)
					note_paths.append(file_path)

>>>>>>> 8f60fd7 (sync wip)
		for file_path in sorted(note_paths, reverse=True):
			st = os.stat(file_path)

			if file_path in self.note_files:
				fields = self.note_files[file_path]
				if st.st_mtime <= fields["mtime"]:
					continue
				fields["mtime"] = st.st_mtime

			else:
				self.add_note_file(file_path)

			self.scan_file(file_path)
			self.update_view()

	def scan_forever(self):
		while not self.cancel_scanning:
			self.scan_dir()
			self.wakeup_event.wait(SCAN_PERIOD)
			self.wakeup_event.clear()


todo_list = TodoList()


class TodoListener(sublime_plugin.ViewEventListener):
	@classmethod
	def is_applicable(cls, settings):
		# print('is_applicable', settings, settings.get('is_todo'))
		return settings.get('todo_base_dir') is not None

	def on_modified(self):
		# print('on_modified', self)
		# print(self.view.sel())

		s = self.view.settings()

		for region in self.view.sel():
			todo_line = self.view.line(region.a)
			todo_text = self.view.substr(todo_line)
			# print(todo_line, todo_text)

			line_re = re.compile(r'\[.\] (.*)')
			todo_m = line_re.match(todo_text)
			if not todo_m:
				print('Not a TODO line, no sync.')
				return
			todo_desc = todo_m.group(1)

			file_heading_line, file_heading_text = todo_line, None
			while file_heading_line.a > 0:
				file_heading_line = self.view.line(sublime.Region(file_heading_line.a - 1))
				file_heading_text = self.view.substr(file_heading_line)
				if file_heading_text.startswith('# '):
					break
			if file_heading_text is None:
				print('No file header for this TODO.')
				return
			file_name = file_heading_text[2:]

			note_date = datetime.datetime.strptime(file_name[:7], '%Y-%m')
			base_dir = s.get("todo_base_dir")
			base_dir = os.path.expanduser(base_dir)
			base_dir = os.path.join(base_dir, str(note_date.year))
			base_dir = os.path.join(base_dir, str(note_date.strftime('%m - %B')))

			file_path = os.path.join(base_dir, file_name)
			# print(file_heading_line, file_heading_text, file_name, file_path)
			
			with open(file_path) as file:
				all_lines = file.readlines()
				
				for line_index, line in enumerate(all_lines):
					line_m = line_re.match(line)
					if line_m:
						line_desc = line_m.group(1)
						if line_desc == todo_desc:
							# print('found at', line_index, line_desc)
							all_lines[line_index] = todo_text + '\n'
							break
			# print(all_lines)

			with open(file_path, 'w') as file:
				file.writelines(all_lines)


class ShowTodoCommand(sublime_plugin.WindowCommand):
	def run(self):
		todo_view = None
		for view in self.window.views():
			if view.name() == 'TODO':
				todo_view = view

		if todo_view is None:
			todo_view = self.window.new_file()
			todo_view.set_name('TODO')

			todo_view.settings().set('gutter', False)
<<<<<<< HEAD
			todo_view.settings().set('is_todo', True)

			s = sublime.load_settings("Ntoes.sublime-settings")
			todo_view.settings().set('todo_base_dir', s.get("base_dir", "~/ntoes/"))

			todo_view.assign_syntax('Packages/Markdown/Markdown.sublime-syntax')
=======
			todo_view.assign_syntax(MARKDOWN_SYNTAX)
>>>>>>> 8f60fd7 (sync wip)
			todo_view.run_command('overwrite', {'characters': '# TODO\n\n'})
			todo_view.run_command('move_to', {"extend": False, "to": "bof"})
			self.window.run_command('new_pane')

		self.window.run_command('set_layout', {
			"cells": [[0, 0, 1, 1], [1, 0, 2, 1]], 
			"cols": [0.0, 0.7, 1.0], "rows": [0.0, 1.0]
			})

		if not todo_list.is_scanning():
			todo_list.todo_view = todo_view
			todo_list.start_scanning()
		else:
			todo_list.wakeup_event.set()


class SetNotesDirCommand(sublime_plugin.WindowCommand):
	def run(self):
		self.window.show_input_panel('Notes Directory', "~/ntoes", self.on_set_notes_dir, None, None)

	def on_set_notes_dir(self, base_dir):
		s = sublime.load_settings("Ntoes.sublime-settings")

		base_dir = os.path.expanduser(base_dir)

		os.makedirs(base_dir, 0o777, True)

		s.set("base_dir", base_dir)

		sublime.save_settings("Ntoes.sublime-settings")


class SyncNotesCommand(sublime_plugin.WindowCommand):
	def exec(self, cmd):
		print(f'$ {cmd}')
		try:
			p = subprocess.run(cmd, check=True, text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			print(p.stdout)
			return p.stdout
		except subprocess.CalledProcessError as e:
			raise f'Failed to execute git command: {cmd}\n{e.stdout}'

	def run(self):
		s = sublime.load_settings("Ntoes.sublime-settings")
		base_dir = s.get("base_dir", "~/ntoes/")
		base_dir = os.path.expanduser(base_dir)

		os.chdir(base_dir)
		self.exec(['git', 'fetch'])
		self.exec(['git', 'merge'])
		status = self.exec(['git', 'status', '--porcelain'])
		if len(status) == 0:
			return
		self.exec(['git', 'add', '.'])
		self.exec(['git', 'commit', '-m', status])
		self.exec(['git', 'push'])


def plugin_unloaded():
	todo_list.stop_scanning()
