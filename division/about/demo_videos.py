from agmodules import cairopath
#import cv2
import math
from moviepy.video.io import ffmpeg_writer
import numpy as np
import tqdm

# Time constants
highlight_time = 0.5 # s
move_time_base = 1 # s
pause_time = 1 # s
fps = 20

# Colours
black = [0, 0, 0]
blue = [0, 68, 153]
red = [255, 0, 0]
white = [255, 255, 255]
highlight = [255, 200, 0]

# Helper functions
def sincos(angle):
	return np.array([math.sin(angle), -math.cos(angle)])

def numbase(n, b, alpha='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
	# https://stackoverflow.com/questions/2267362
	if b == 1: return n*alpha[1]
	if n == 0: return alpha[0]
	return numbase(n//b, b, alpha).lstrip(alpha[0]) + alpha[n % b]

def int_from_digits(arr, b):
	n = 0
	for i, digit in enumerate(reversed(arr)):
		n += b**i * digit
	return n

def arrow(canvas, size, sw):
	return canvas.path().M(sw/2, size).H(size).L(0, -size).L(-size, size).H(-sw/2) \
	             .stroke(white, width=sw, opacity=0.8, keep=True)

def lerp(colour1, colour2, x):
	return [round((1-x)*v1+x*v2) for v1, v2 in zip(colour1, colour2)]

def ease(t):
	t = min(t, 1)
	return (1-math.cos(t*math.pi))/2

class Diagram:
	def __init__(self, number, modulus=7, base=10, width=900, height=600, *, quotients=False, base_convert=False, inner_base=True, outer_base=False):
		self.number = number
		self.n = modulus
		self.b = base
		self.width = width
		self.height = height
		self.quotients = quotients or base_convert
		self.base_convert = base_convert
		self.inner_base = inner_base
		self.outer_base = outer_base

		# Calculated coordinates & sizes
		self.poly_r = height*0.3
		self.pts = [sincos(i*2*math.pi/self.n) for i in range(self.n)]
		self.links = [(self.b*i)%self.n for i in range(self.n)]
		self.quots = [(self.b*i)//self.n for i in range(self.n)]

		self.max_point_size = self.height/60
		self.max_stroke_width = self.height/120
		self.max_font_size = self.height/10

		self.edge = self.poly_r if self.n == 1 else np.linalg.norm(self.pts[1]-self.pts[0])*self.poly_r
		self.stroke_width = min(self.max_stroke_width, self.edge/20)
		self.point_size = min(self.max_point_size, self.edge/8)
		self.self_size = self.point_size + 1.5*self.stroke_width
		self.arrow_size = self.stroke_width*2.5
		self.arrow_dist = max(self.edge/3, self.self_size+self.stroke_width+self.arrow_size)
		self.arrow_offset = self.n*[0]
		self.dr = self.stroke_width*0.75*min(2, 1/math.cos(math.pi/self.n))
		self.font_size = min(self.edge/2, self.max_font_size)

		if self.base_convert:
			self.converted_digits = []
			self.converted_length = len(numbase(self.number, self.n))
			self.converted_digit_colours = [None]*self.converted_length

		self.outer_colours = [None]*self.n
		self.inner_colours = [None]*self.n
		self.remainder_colours = [None]*self.n

		self.set_number(number)
		self.reset_animation_state()

	def set_number(self, n, pad_length=None):
		self.number = n
		self.digits = numbase(n, self.b)
		self.quotient_digits = []

		self.pad_digits = 0
		if pad_length and pad_length > len(self.digits):
			self.pad_digits = pad_length - len(self.digits)

		rel_spacing = 1/3 # ratio of spacing to character width
		self.digits_width = (self.width - self.height)*0.75
		self.digit_width = self.digits_width/((len(self.digits) + self.pad_digits - 1)*(1 + rel_spacing) + 1)
		self.digit_spacing = self.digit_width/3
		self.digit_height = self.digit_width * 1.5
		self.digits_x = (self.width - self.height)/2 - self.digits_width/2 + self.pad_digits*(self.digit_width + self.digit_spacing)
		self.digits_y = self.height/2 - self.digit_height/2
		if self.quotients:
			self.digits_y -= (self.digit_height + self.digit_spacing)/2
			self.quotients_y = self.digits_y + self.digit_height + self.digit_spacing

		if self.base_convert:
			self.converted_digit_width = self.digits_width/((self.converted_length - 1)*(1 + rel_spacing) + 1)
			self.converted_digit_spacing = self.converted_digit_width/3
			self.converted_digit_height = self.converted_digit_width * 1.5
			self.converted_x = (self.width - self.height)/2 + self.digits_width/2 - self.converted_digit_width # right-aligned
			self.digits_y -= (self.converted_digit_height + self.digit_spacing)/2
			self.quotients_y -= (self.converted_digit_height + self.digit_spacing)/2
			self.converted_y = self.quotients_y + self.digit_height + self.digit_spacing
		
		self.digit_colours = [None]*len(self.digits)
		self.quotient_digit_colours = [None]*len(self.digits)

	def reset_animation_state(self):
		for i in range(self.n):
			self.outer_colours[i] = black
			self.inner_colours[i] = blue
			self.remainder_colours[i] = black
		for i in range(len(self.digits)):
			self.digit_colours[i] = black
			self.quotient_digit_colours[i] = white
		self.set_dot_position(0)
		self.dot_colour = black
		self.digit_box_colour = white
		self.digit_box_position = 0
		self.quotient_digits = []

	def number_in_base(self, number, setting):
		if setting == 'modulus':
			return numbase(number, self.n)
		elif setting:
			return numbase(number, self.b)
		else:
			return str(number)

	def set_dot_position(self, i):
		self.dot_position = i % self.n ## !
		angle = i*2*math.pi/self.n
		r = self.poly_r
		# Follow polygon for non-integer i
		if i % 1 != 0:
			r = math.sqrt((r*math.cos(math.pi/self.n))**2 + (abs(i%1-0.5)*self.edge)**2)
		self.dot_coords = r*sincos(angle)

	def draw(self):
		canvas = cairopath.Canvas(self.width, self.height, white, surfacetype='image')
		context = canvas.context

		with canvas.translate(self.width-self.height/2, self.height/2):
			# Black outer polygon & black arrows
			if self.n>1:
				for i in range(self.n):
					canvas.path().M(*(self.poly_r+self.dr)*self.pts[i]).L(*(self.poly_r+self.dr)*self.pts[(i+1)%self.n]) \
											.stroke(self.outer_colours[i], width=self.stroke_width, join=1)
				for i in range(self.n):
					if i-self.links[i] in [-1, self.n-1]:
						# blue arrow goes one step clockward & would overlap black one
						self.arrow_offset[i] = -min(1.5*self.arrow_size, self.edge/15)
					with canvas.translate(*(self.poly_r+self.dr)*self.pts[i]) \
					           .rotate((i+0.5)*360/self.n+90) \
					           .translate(0, -self.arrow_dist+self.arrow_offset[i]):
						arrow(canvas, self.arrow_size, self.stroke_width).fill(self.outer_colours[i])
			# Blue lines & circles
			for i in range(self.n):
				if i == self.links[i]:
					canvas.circle(self.self_size, *self.poly_r*self.pts[i]).stroke(self.inner_colours[i], width=self.stroke_width)
				else:
					canvas.path().M(*(self.poly_r-self.dr)*self.pts[i]).L(*(self.poly_r-self.dr)*self.pts[self.links[i]]) \
					             .stroke(self.inner_colours[i], width=self.stroke_width, cap=1)
			# Text, vertex dots & blue arrows
			for i in range(self.n):
				number_text = self.number_in_base(i, self.outer_base)
				context.set_font_size(self.font_size)
				dims = context.text_extents(number_text)
				text_diag = 1/max(abs(self.pts[i][0])/dims[2], abs(self.pts[i][1])/dims[3])
				if dims[2]>self.edge:
					context.set_font_size(self.font_size*self.edge/dims[2])
					dims = context.text_extents(number_text)
					text_diag = 1/max(abs(self.pts[i][0])/dims[2], abs(self.pts[i][1])/dims[3])
				text_r = self.poly_r + self.self_size + 2*self.stroke_width + text_diag/2
				with canvas.translate(*text_r*self.pts[i]) \
				           .translate(-dims[0]-dims[2]/2, -dims[1]-dims[3]/2):
					canvas._setcolor(context, self.remainder_colours[i])
					context.show_text(number_text)
				if i!=self.links[i]:
					link_dir = math.pi-math.atan2(*(self.pts[self.links[i]]-self.pts[i]))
					with canvas.translate(*(self.poly_r-self.dr)*self.pts[i]) \
					           .rotate(link_dir, rad=True) \
					           .translate(0, -self.arrow_dist-self.arrow_offset[i]):
						arrow(canvas, self.arrow_size, self.stroke_width).fill(self.inner_colours[i])
				if self.quotients and i>0:
					number_text = self.number_in_base(self.quots[i], self.inner_base)
					context.set_font_size(min(0.9*self.font_size, 0.6*self.max_font_size))
					dims = context.text_extents(number_text)
					if i == self.links[i]:
						text_diag = 1/max(abs(self.pts[i][0])/dims[2], abs(self.pts[i][1])/dims[3])
						text_pos = (self.poly_r-self.self_size-self.stroke_width-text_diag/2)*self.pts[i]
					else:
						lr = 1 if (link_dir-(i*2*math.pi/self.n)) % (2*math.pi) <= math.pi else -1
						text_dir = link_dir+lr*1*math.pi/2
						text_diag = 1/max(abs(math.sin(text_dir))/dims[2], \
						            abs(math.cos(text_dir))/dims[3])
						text_pos = (self.poly_r-self.dr)*self.pts[i] + (self.arrow_dist-self.arrow_size/2)*sincos(link_dir) \
						         + (self.arrow_size+text_diag/2)*sincos(text_dir)
					context.new_path()
					with canvas.translate(*text_pos) \
					           .translate(-dims[0]-dims[2]/2, -dims[1]-dims[3]/2):
						context.text_path(number_text)
						canvas.stroke(white, width=self.stroke_width, opacity=0.8, keep=True) \
						      .fill(self.inner_colours[i])
				canvas.circle(self.point_size, *self.poly_r*self.pts[i]) \
				      .fill(black)
			# Red dot
			if self.dot_coords is not None:
				canvas.circle(self.point_size, *self.dot_coords).fill(self.dot_colour)

		# Digits & box
		box_x = self.digits_x + self.digit_box_position*(self.digit_width+self.digit_spacing) - self.digit_spacing/2
		box_y = self.digits_y - self.digit_spacing/2
		canvas.rect(self.digit_width + self.digit_spacing, self.digit_height + self.digit_spacing, x=box_x, y=box_y) \
		      .stroke(self.digit_box_colour, width=self.stroke_width)

		context.set_font_size(self.digit_height)
		for i, digit in enumerate(self.digits):
			dims = context.text_extents(digit)
			x = self.digits_x + i*(self.digit_width+self.digit_spacing) + self.digit_width/2 - dims[0] - dims[2]/2
			y = self.digits_y + self.digit_height/2 - dims[1] - dims[3]/2
			with canvas.translate(x, y):
				context.text_path(digit)
				canvas.fill(self.digit_colours[i])
		if self.quotients:
			for i, digit in enumerate(self.quotient_digits):
				digit = numbase(digit, self.b)
				dims = context.text_extents(digit)
				x = self.digits_x + i*(self.digit_width+self.digit_spacing) + self.digit_width/2 - dims[0] - dims[2]/2
				y = self.quotients_y + self.digit_height/2 - dims[1] - dims[3]/2
				with canvas.translate(x, y):
					context.text_path(digit)
					canvas.fill(self.quotient_digit_colours[i])
		if self.base_convert and self.converted_digits:
			for i, digit in enumerate(self.converted_digits):
				digit = numbase(digit, self.n)
				dims = context.text_extents(digit)
				x = self.converted_x - i*(self.converted_digit_width+self.converted_digit_spacing) + self.converted_digit_width/2 - dims[0] - dims[2]/2
				y = self.converted_y + self.converted_digit_height/2 - dims[1] - dims[3]/2
				with canvas.translate(x, y):
					context.text_path(digit)
					canvas.fill(self.converted_digit_colours[i])

		return canvas.img()

	def animate_colour(self, attrib, index, end_colour):
		if index is None: # animate self.attrib
			start_colour = getattr(self, attrib)
		else: # animate self.attrib[index]
			if type(index) is int:
				index = [index]
			array = getattr(self, attrib)
			start_colours = {i:array[i] for i in index}
		def frame(t, dur):
			x = ease(t/(dur-1/fps))
			if index is None: # animate self.attrib
				setattr(self, attrib, lerp(start_colour, end_colour, x))
			else: # animate self.attrib[index]
				for i in index:
					array[i] = lerp(start_colours[i], end_colour, x)
			return self.draw()
		return frame, None

	def animate_dot_move(self, start_index, end_index, around=True):
		start_index = round(self.dot_position)
		if around: # black arrow path
			def frame(t, dur):
				x = ease(t/(dur-1/fps))
				index = (1-x)*start_index + x*end_index
				self.set_dot_position(index)
				return self.draw()
		else: # blue arrow path
			coord1 = self.poly_r*self.pts[start_index]
			coord2 = self.poly_r*self.pts[end_index%self.n]
			def frame(t, dur):
				x = ease(t/(dur-1/fps))
				self.dot_coords = (1-x)*coord1 + x*coord2
				return self.draw()
		# Set end state
		def after():
			self.set_dot_position(end_index%self.n)
		return frame, after

	def animate_box_move(self, start_position, end_position):
		start_position = self.digit_box_position
		def frame(t, dur):
			x = ease(t/(dur-1/fps))
			self.digit_box_position = (1-x)*start_position + x*end_position
			return self.draw()
		return frame, None

	def animate_quotient_digit(self, digit_position, digit, end_colour):
		if self.quotients:
			self.quotient_digits.append(digit)
			self.quotient_digit_colours[digit_position] = white
			return self.animate_colour('quotient_digit_colours', digit_position, end_colour)
		else:
			return None, None

	def animate_converted_digit(self, digit_position, digit, end_colour):
		if self.converted_digits is not None:
			self.converted_digits.append(digit)
			self.converted_digit_colours[digit_position] = white
			return self.animate_colour('converted_digit_colours', digit_position, end_colour)
		else:
			return None, None

	def animate_quotient_increment(self, digit_position, digit, highlight_colour):
		self.quotient_digits[digit_position] += 1;
		# Highlight digit instantaneously and fade back to previous colour
		end_quotient_colour = self.quotient_digit_colours[digit_position]
		self.quotient_digit_colours[digit_position] = highlight_colour;
		return self.animate_colour('quotient_digit_colours', digit_position, end_quotient_colour)

	def animate_quotient_move(self):
		start_position = self.quotients_y
		end_position = self.quotients_y - self.digit_height - self.digit_spacing
		def frame(t, dur):
			x = ease(t/(dur-1/fps))
			self.quotients_y = (1-x)*start_position + x*end_position
			return self.draw()
		return frame, None


class VideoWriter:
	def __init__(self, diagram, filename, fps):
		self.diagram = diagram
		self.filename = filename
		self.fps = fps
		#self.writer = cv2.VideoWriter(self.filename, cv2.VideoWriter_fourcc(*'avc1'), self.fps, (self.diagram.width, self.diagram.height))
		self.writer = ffmpeg_writer.FFMPEG_VideoWriter(self.filename, (self.diagram.width, self.diagram.height), self.fps)
		self.frames = 0
		self.time = 0
		self.progress = tqdm.tqdm(unit=' frames')

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		self.save()

	def save(self):
		#self.writer.release()
		self.writer.close()
		self.progress.close()

	def frame(self, img):
		#img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
		#self.writer.write(img)
		self.writer.write_frame(img)
		self.frames += 1
		self.time += 1/self.fps
		self.progress.update()
		self.progress.set_postfix({'video time': '{:02.0f}:{:02.0f}'.format(self.time//60, self.time%60)})

	def static_image(self, img, duration=pause_time):
		start_time = self.time
		while self.time - start_time < duration:
			self.frame(img)

	def animation(self, functions, duration):#=highlight_time
		frame_fun, after_fun = functions
		start_time = self.time
		if frame_fun:
			while self.time - start_time < duration:
				img = frame_fun(self.time - start_time, duration)
				self.frame(img)
		if after_fun:
			after_fun()

	def animation_sync(self, functions_list, duration):#=highlight_time
		start_time = self.time
		frame_funs = [f[0] for f in functions_list if f[0]]
		after_funs = [f[1] for f in functions_list if f[1]]
		if len(frame_funs):
			while self.time - start_time < duration:
				for frame_fun in frame_funs:
					img = frame_fun(self.time - start_time, duration)
				self.frame(img)
		for after_fun in after_funs:
			after_fun()


def create_demo(filename, number, modulus=7, base=10, quotients=False, base_convert=False):
	diagram = Diagram(number, modulus, base, quotients=quotients, base_convert=base_convert, outer_base=base_convert and 'modulus')
	with VideoWriter(diagram, filename, fps) as writer:
		division_demo(diagram, writer)

		if base_convert:
			num_digits = len(diagram.digits)
			remainder = round(diagram.dot_position)
			quotient = int_from_digits(diagram.quotient_digits, diagram.b)
			i = 0
			while True:
				# Add converted digit & move quotient to input
				writer.animation(diagram.animate_converted_digit(i, remainder, red), duration=highlight_time)
				writer.static_image(diagram.draw(), duration=pause_time)
				writer.animation_sync((diagram.animate_colour('remainder_colours', round(diagram.dot_position), black),
				                       diagram.animate_colour('dot_colour', None, black)), duration=highlight_time)
				writer.static_image(diagram.draw(), duration=2*pause_time)

				if quotient == 0:
					break

				quotient_leading_zeros = next((j for j,digit in enumerate(diagram.quotient_digits) if digit > 0), len(diagram.quotient_digits))
				writer.animation_sync((diagram.animate_colour('digit_colours', range(len(diagram.digits)), white),
				                       diagram.animate_colour('quotient_digit_colours', range(quotient_leading_zeros), white)), duration=highlight_time)
				writer.static_image(diagram.draw(), duration=pause_time/2)
				writer.animation_sync((diagram.animate_colour('quotient_digit_colours', range(quotient_leading_zeros, len(diagram.quotient_digits)), black),
				                       diagram.animate_quotient_move()), duration=move_time_base)
				writer.static_image(diagram.draw(), duration=pause_time)

				diagram.set_number(quotient, pad_length=num_digits)
				diagram.reset_animation_state()
				division_demo(diagram, writer)
				remainder = round(diagram.dot_position)
				quotient = int_from_digits(diagram.quotient_digits, diagram.b)
				i += 1

			# Show original number
			writer.animation_sync((diagram.animate_colour('digit_colours', range(len(diagram.digits)), white),
														 diagram.animate_colour('quotient_digit_colours', range(len(diagram.quotient_digits)), white)), duration=highlight_time)
			# writer.static_image(diagram.draw(), duration=pause_time/2)
			# diagram.set_number(number)
			# for i in range(len(diagram.digits)):
				# diagram.digit_colours[i] = white
			# writer.animation(diagram.animate_colour('digit_colours', range(len(diagram.digits)), black), duration=highlight_time)

		writer.static_image(diagram.draw(), duration=3*pause_time)


def division_demo(diagram, writer):
		# Colour dot & box
		writer.static_image(diagram.draw())
		writer.animation(diagram.animate_colour('dot_colour', None, red), duration=highlight_time)
		writer.static_image(diagram.draw(), duration=pause_time/2)
		writer.animation_sync((diagram.animate_colour('digit_box_colour', None, blue),
		                       diagram.animate_quotient_digit(0, 0, blue)), duration=highlight_time)
		writer.static_image(diagram.draw())

		for i, digit in enumerate(diagram.digits):
			digit = int(digit, base=diagram.b)
			if i > 0: # Shift to next digit (blue arrow)
				# Highlight box & blue arrow
				start_pos = round(diagram.dot_position)# % diagram.n
				writer.animation(diagram.animate_colour('digit_box_colour', None, highlight), duration=highlight_time)
				writer.animation(diagram.animate_colour('inner_colours', start_pos, highlight), duration=highlight_time)
				# Move dot
				writer.static_image(diagram.draw(), duration=pause_time/2)
				writer.animation_sync((diagram.animate_dot_move(start_pos, diagram.links[start_pos], False),
				                       diagram.animate_box_move(i-1, i),
				                       diagram.animate_quotient_digit(i, diagram.quots[start_pos], highlight)), duration=move_time_base)
				# Remove highlight
				writer.animation_sync((diagram.animate_colour('inner_colours', start_pos, blue),
				                       diagram.animate_colour('digit_box_colour', None, blue),
				                       diagram.animate_colour('quotient_digit_colours', i, blue)), duration=highlight_time)
				# Pause
				writer.static_image(diagram.draw())

			# Highlight digit & black arrows
			writer.animation(diagram.animate_colour('digit_colours', i, highlight), duration=highlight_time)
			writer.static_image(diagram.draw(), duration=pause_time/2)
			start_pos = round(diagram.dot_position)
			for j in range(digit):
				if j > 0 and j % diagram.n == 0:
					# end of full rotation; darken arrows before highlighting remaining ones
					writer.animation(diagram.animate_colour('outer_colours', range(diagram.n), lerp(black, highlight, 0.5)), duration=highlight_time/2)
				writer.animation(diagram.animate_colour('outer_colours', (start_pos+j)%diagram.n, highlight), duration=highlight_time)
				if diagram.quotients and (start_pos + j + 1) % diagram.n == 0:
					# passing 0; increment quotient
					writer.animation(diagram.animate_colour('remainder_colours', 0, highlight), duration=highlight_time)
					writer.animation_sync((diagram.animate_quotient_increment(i, diagram.quotient_digits[i]+1, highlight),
					                       diagram.animate_colour('remainder_colours', 0, black)), duration=2*highlight_time)
			# Move dot
			writer.static_image(diagram.draw(), duration=pause_time/2)
			move_time = move_time_base*math.sqrt(digit)
			writer.animation(diagram.animate_dot_move(start_pos, start_pos+digit), duration=move_time)
			# Remove highlights
			writer.animation_sync((diagram.animate_colour('outer_colours', [(start_pos+j)%diagram.n for j in range(digit)], black),
			                       diagram.animate_colour('digit_colours', i, black)), duration=highlight_time)
			# Pause
			writer.static_image(diagram.draw())

		# Highlight answer
		writer.animation(diagram.animate_colour('digit_box_colour', None, white), duration=highlight_time)
		writer.static_image(diagram.draw())
		writer.animation(diagram.animate_colour('remainder_colours', round(diagram.dot_position), red), duration=highlight_time)


create_demo('demo_divisibility.mp4', number=1729, modulus=7, base=10, quotients=False)
create_demo('demo_division.mp4', number=3551, modulus=13, base=10, quotients=True)
create_demo('demo_base_convert.mp4', number=418, modulus=16, base=10, base_convert=True)
