import datetime
import os

import sublime
import sublime_plugin

# To open a file at a line number:
# window.open_file("{}:{}:{}".format(fname, row, col), sublime.ENCODED_POSITION)

class NewNoteCommand(sublime_plugin.WindowCommand):
	def run(self):
		self.window.show_input_panel("New Note", datetime.date.today().isoformat(), self.on_new_note, None, None)

	def on_new_note(self, title):		
		note_view = self.window.new_file()
		note_view.set_name(title + '.md')
		note_view.run_command('append', {'characters': '# {}\n\n'.format(title)})
		note_view.run_command('move_to', {'to': 'eof', 'extend': False})
		note_view.assign_syntax('Packages/Markdown/Markdown.sublime-syntax')

		s = sublime.load_settings("Ntoes.sublime-settings")

		note_date = datetime.datetime.strptime(title[:7], '%Y-%m')

		base_dir = s.get("base_dir", "~/ntoes/")
		base_dir = os.path.expanduser(base_dir)
		base_dir = os.path.join(base_dir, str(note_date.year))
		base_dir = os.path.join(base_dir, str(note_date.strftime('%m - %B')))

		os.makedirs(base_dir, 0o777, True)

		note_view.settings().set('default_dir', base_dir)


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
			elif old_str[0] == '[' and old_str[2:4] == '] ':
				self.view.replace(edit, old_region, '[X] ')
			else:
				self.view.insert(edit, region.begin(), '[ ] ')


	def description(self):
		return "Toggles the current line's TODO item."


class ShowTodoCommand(sublime_plugin.WindowCommand):
	def run(self):
		# sublime.run_command('show_panel', {
		# 	'panel': 'find_in_files',
		# 	'regular_expression': False,
		# 	'case_sensitive': False,
		# 	'whole_word': True,
		# 	'in_selection': False,
		# 	'wrap': True,
		# 	'highlight_matches': False
		# 	})
		# sublime.run_command('find_all', {
		# 	'close_panel': True
		# 	})
		# self.window.run_command('set_layout', {
		# 	"cells": [[0, 0, 1, 1], [1, 0, 2, 1]], 
		# 	"cols": [0.0, 0.7, 1.0], "rows": [0.0, 1.0]
		# 	})

		todo_view = None
		for view in self.window.views():
			if view.name() == 'TODO':
				todo_view = view

		if todo_view is None:
			todo_view = self.window.new_file()
			todo_view.set_name('TODO')
			todo_view.assign_syntax('Packages/Markdown/Markdown.sublime-syntax')
			self.window.run_command('new_pane')

		self.window.run_command('set_layout', {
			"cells": [[0, 0, 1, 1], [1, 0, 2, 1]], 
			"cols": [0.0, 0.7, 1.0], "rows": [0.0, 1.0]
			})

		self.scan_todo(todo_view)

	def scan_todo(self, todo_view):
		todo_view.run_command('select_all')
		todo_view.run_command('right_delete')

		s = sublime.load_settings("Ntoes.sublime-settings")

		base_dir = s.get("base_dir", "~/ntoes/")
		base_dir = os.path.expanduser(base_dir)

		for dirpath, dirnames, filenames in os.walk(base_dir):
			for file_name in filenames:
				if file_name.endswith('.md'):
					file_path = os.path.join(dirpath, file_name)
					print(file_path)
					with open(file_path) as file:
						first_todo_in_file = True
						for line in file.readlines():
							if '[ ]' in line:
								if first_todo_in_file:
									todo_view.run_command('append', {'characters': '# ' + file_name + '\n\n'})
									first_todo_in_file = False
								todo_view.run_command('append', {'characters': line})
						if not first_todo_in_file:
							todo_view.run_command('append', {'characters': '\n'})



class SetNotesDirCommand(sublime_plugin.ApplicationCommand):
	def run(self):
		date_title = datetime.date.today().isoformat()
		self.window.show_input_panel('Notes Directory', "~/ntoes", self.on_set_notes_dir, None, None)

	def on_set_notes_dir(self, base_dir):
		s = sublime.load_settings("Ntoes.sublime-settings")

		base_dir = os.path.expanduser(base_dir)

		os.makedirs(base_dir, 0o777, True)

		s.set("base_dir", base_dir)

		sublime.save_settings("Ntoes.sublime-settings")
