# /*#########################################################################
#
# The PyMca X-Ray Fluorescence Toolkit
#
# Copyright (c) 2004-2014 European Synchrotron Radiation Facility
#
# This file is part of the PyMca X-ray Fluorescence Toolkit developed at
# the ESRF by the Software group.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# ###########################################################################*/
__author__ = "T. Vincent - ESRF Data Analysis"
__contact__ = "thomas.vincent@esrf.fr"
__license__ = "MIT"
__copyright__ = "European Synchrotron Radiation Facility, Grenoble, France"
__doc__ = """
This module provides classes to render 2D lines and scatter plots
"""


# import ######################################################################

from .gl import *  # noqa
import numpy as np
import math
from collections import defaultdict
from .GLContext import getGLContext
from .GLSupport import Program, buildFillMaskIndices
from .GLVertexBuffer import createVBOFromArrays, VBOAttrib

try:
    from ....ctools import minMax
except ImportError:
    from PyMca5.PyMcaGraph.ctools import minMax

_MPL_NONES = None, 'None', '', ' '


# fill ########################################################################

class _Fill2D(object):
    _LINEAR, _LOG10_X, _LOG10_Y, _LOG10_X_Y = 0, 1, 2, 3

    _SHADER_SRCS = {
        'vertexTransforms': {
            _LINEAR: """
        vec4 transformXY(float x, float y) {
            return vec4(x, y, 0.0, 1.0);
        }
        """,
            _LOG10_X: """
        const float oneOverLog10 = 0.43429448190325176;

        vec4 transformXY(float x, float y) {
            return vec4(oneOverLog10 * log(x), y, 0.0, 1.0);
        }
        """,
            _LOG10_Y: """
        const float oneOverLog10 = 0.43429448190325176;

        vec4 transformXY(float x, float y) {
            return vec4(x, oneOverLog10 * log(y), 0.0, 1.0);
        }
        """,
            _LOG10_X_Y: """
        const float oneOverLog10 = 0.43429448190325176;

        vec4 transformXY(float x, float y) {
            return vec4(oneOverLog10 * log(x),
                        oneOverLog10 * log(y),
                        0.0, 1.0);
        }
        """
        },
        'vertex': """
        #version 120

        uniform mat4 matrix;
        attribute float xPos;
        attribute float yPos;

        %s

        void main(void) {
            gl_Position = matrix * transformXY(xPos, yPos);
        }
        """,
        'fragment': """
        #version 120

        uniform vec4 color;

        void main(void) {
            gl_FragColor = color;
        }
        """
    }

    _programs = defaultdict(dict)

    def __init__(self, xFillVboData=None, yFillVboData=None,
                 xMin=None, yMin=None, xMax=None, yMax=None,
                 color=(0., 0., 0., 1.)):
        self.xFillVboData = xFillVboData
        self.yFillVboData = yFillVboData
        self.xMin, self.yMin = xMin, yMin
        self.xMax, self.yMax = xMax, yMax
        self.color = color

        self._bboxVertices = None
        self._indices = None

    @classmethod
    def _getProgram(cls, transform):
        context = getGLContext()
        programs = cls._programs[transform]
        try:
            prgm = programs[context]
        except KeyError:
            srcs = cls._SHADER_SRCS
            vertexShdr = srcs['vertex'] % srcs['vertexTransforms'][transform]
            prgm = Program(vertexShdr, srcs['fragment'])
            programs[context] = prgm
        return prgm

    def prepare(self):
        if self._indices is None:
            self._indices = buildFillMaskIndices(self.xFillVboData.size)
            self._indicesType = numpyToGLType(self._indices.dtype)

        if self._bboxVertices is None:
            yMin, yMax = min(self.yMin, 1e-32), max(self.yMax, 1e-32)
            self._bboxVertices = np.array(((self.xMin, self.xMin,
                                            self.xMax, self.xMax),
                                           (yMin, yMax, yMin, yMax)),
                                          dtype=np.float32)

    def render(self, matrix, isXLog, isYLog):
        self.prepare()

        if isXLog:
            transform = self._LOG10_X_Y if isYLog else self._LOG10_X
        else:
            transform = self._LOG10_Y if isYLog else self._LINEAR

        prog = self._getProgram(transform)
        prog.use()

        glUniformMatrix4fv(prog.uniforms['matrix'], 1, GL_TRUE, matrix)

        glUniform4f(prog.uniforms['color'], *self.color)

        xPosAttrib = prog.attributes['xPos']
        yPosAttrib = prog.attributes['yPos']

        glEnableVertexAttribArray(xPosAttrib)
        self.xFillVboData.setVertexAttrib(xPosAttrib)

        glEnableVertexAttribArray(yPosAttrib)
        self.yFillVboData.setVertexAttrib(yPosAttrib)

        # Prepare fill mask
        glEnable(GL_STENCIL_TEST)
        glStencilMask(1)
        glStencilFunc(GL_ALWAYS, 1, 1)
        glStencilOp(GL_INVERT, GL_INVERT, GL_INVERT)
        glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE)
        glDepthMask(GL_FALSE)

        glDrawElements(GL_TRIANGLE_STRIP, self._indices.size,
                       self._indicesType, self._indices)

        glStencilFunc(GL_EQUAL, 1, 1)
        glStencilOp(GL_ZERO, GL_ZERO, GL_ZERO)  # Reset stencil while drawing
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE)
        glDepthMask(GL_TRUE)

        glVertexAttribPointer(xPosAttrib, 1, GL_FLOAT, GL_FALSE, 0,
                              self._bboxVertices[0])
        glVertexAttribPointer(yPosAttrib, 1, GL_FLOAT, GL_FALSE, 0,
                              self._bboxVertices[1])
        glDrawArrays(GL_TRIANGLE_STRIP, 0, self._bboxVertices[0].size)

        glDisable(GL_STENCIL_TEST)


# line ########################################################################

SOLID, DASHED = '-', '--'


class _Lines2D(object):
    STYLES = SOLID, DASHED
    """Supported line styles (missing '-.' ':')"""

    _LINEAR, _LOG10_X, _LOG10_Y, _LOG10_X_Y = 0, 1, 2, 3

    _SHADER_SRCS = {
        'vertexTransforms': {
            _LINEAR: """
        vec4 transformXY(float x, float y) {
            return vec4(x, y, 0.0, 1.0);
        }
        """,
            _LOG10_X: """
        const float oneOverLog10 = 0.43429448190325176;

        vec4 transformXY(float x, float y) {
            return vec4(oneOverLog10 * log(x), y, 0.0, 1.0);
        }
        """,
            _LOG10_Y: """
        const float oneOverLog10 = 0.43429448190325176;

        vec4 transformXY(float x, float y) {
            return vec4(x, oneOverLog10 * log(y), 0.0, 1.0);
        }
        """,
            _LOG10_X_Y: """
        const float oneOverLog10 = 0.43429448190325176;

        vec4 transformXY(float x, float y) {
            return vec4(oneOverLog10 * log(x),
                        oneOverLog10 * log(y),
                        0.0, 1.0);
        }
        """
        },
        SOLID: {
            'vertex': ("""
        #version 120

        uniform mat4 matrix;
        attribute float xPos;
        attribute float yPos;
        attribute vec4 color;

        varying vec4 vColor;
        """,
                       """
        void main(void) {
            gl_Position = matrix * transformXY(xPos, yPos);
            vColor = color;
        }
        """),
            'fragment': """
        #version 120

        varying vec4 vColor;

        void main(void) {
            gl_FragColor = vColor;
        }
        """
        },


        # Limitation: Dash using an estimate of distance in screen coord
        # to avoid computing distance when viewport is resized
        # results in inequal dashes when viewport aspect ratio is far from 1
        DASHED: {
            'vertex': ("""
        #version 120

        uniform mat4 matrix;
        uniform vec2 halfViewportSize;
        attribute float xPos;
        attribute float yPos;
        attribute vec4 color;
        attribute float distance;

        varying float vDist;
        varying vec4 vColor;
        """,
                       """
        void main(void) {
            gl_Position = matrix * transformXY(xPos, yPos);
            //Estimate distance in pixels
            vec2 probe = vec2(matrix * vec4(1., 1., 0., 0.)) *
                         halfViewportSize;
            float pixelPerDataEstimate = length(probe)/sqrt(2.);
            vDist = distance * pixelPerDataEstimate;
            vColor = color;
        }
        """),
            'fragment': """
        #version 120

        uniform float dashPeriod;

        varying float vDist;
        varying vec4 vColor;

        void main(void) {
            if (mod(vDist, dashPeriod) > 0.5 * dashPeriod) {
                discard;
            } else {
                gl_FragColor = vColor;
            }
        }
        """
        }
    }

    _programs = defaultdict(dict)

    def __init__(self, xVboData=None, yVboData=None,
                 colorVboData=None, distVboData=None,
                 style=SOLID, color=(0., 0., 0., 1.),
                 width=1, dashPeriod=20):
        self.xVboData = xVboData
        self.yVboData = yVboData
        self.distVboData = distVboData
        self.colorVboData = colorVboData
        self.useColorVboData = colorVboData is not None

        self.color = color
        self.width = width
        self.style = style
        self.dashPeriod = dashPeriod

    @property
    def style(self):
        return self._style

    @style.setter
    def style(self, style):
        if style in _MPL_NONES:
            self._style = None
            self.render = self._renderNone
        else:
            assert style in self.STYLES
            self._style = style
            if style == SOLID:
                self.render = self._renderSolid
            elif style == DASHED:
                self.render = self._renderDash

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, width):
        # try:
        #    widthRange = self._widthRange
        # except AttributeError:
        #    widthRange = glGetFloatv(GL_ALIASED_LINE_WIDTH_RANGE)
        #    # Shared among contexts, this should be enough..
        #    _Lines2D._widthRange = widthRange
        # assert width >= widthRange[0] and width <= widthRange[1]
        self._width = width

    @classmethod
    def _getProgram(cls, transform, style):
        context = getGLContext()
        programs = cls._programs[(transform, style)]
        try:
            prgm = programs[context]
        except KeyError:
            sources = cls._SHADER_SRCS[style]
            vertexShdr = sources['vertex'][0] + \
                cls._SHADER_SRCS['vertexTransforms'][transform] + \
                sources['vertex'][1]
            prgm = Program(vertexShdr,
                           sources['fragment'])
            programs[context] = prgm
        return prgm

    @classmethod
    def init(cls):
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)

    def _renderNone(self, matrix, isXLog, isYLog):
        pass

    render = _renderNone  # Overridden in style setter

    def _renderSolid(self, matrix, isXLog, isYLog):
        if isXLog:
            transform = self._LOG10_X_Y if isYLog else self._LOG10_X
        else:
            transform = self._LOG10_Y if isYLog else self._LINEAR

        prog = self._getProgram(transform, SOLID)
        prog.use()

        glEnable(GL_LINE_SMOOTH)

        glUniformMatrix4fv(prog.uniforms['matrix'], 1, GL_TRUE, matrix)

        colorAttrib = prog.attributes['color']
        if self.useColorVboData and self.colorVboData is not None:
            glEnableVertexAttribArray(colorAttrib)
            self.colorVboData.setVertexAttrib(colorAttrib)
        else:
            glDisableVertexAttribArray(colorAttrib)
            glVertexAttrib4f(colorAttrib, *self.color)

        xPosAttrib = prog.attributes['xPos']
        glEnableVertexAttribArray(xPosAttrib)
        self.xVboData.setVertexAttrib(xPosAttrib)

        yPosAttrib = prog.attributes['yPos']
        glEnableVertexAttribArray(yPosAttrib)
        self.yVboData.setVertexAttrib(yPosAttrib)

        glLineWidth(self.width)
        glDrawArrays(GL_LINE_STRIP, 0, self.xVboData.size)

        glDisable(GL_LINE_SMOOTH)

    def _renderDash(self, matrix, isXLog, isYLog):
        if isXLog:
            transform = self._LOG10_X_Y if isYLog else self._LOG10_X
        else:
            transform = self._LOG10_Y if isYLog else self._LINEAR

        prog = self._getProgram(transform, DASHED)
        prog.use()

        glEnable(GL_LINE_SMOOTH)

        glUniformMatrix4fv(prog.uniforms['matrix'], 1, GL_TRUE, matrix)
        x, y, viewWidth, viewHeight = glGetFloat(GL_VIEWPORT)
        glUniform2f(prog.uniforms['halfViewportSize'],
                    0.5 * viewWidth, 0.5 * viewHeight)

        glUniform1f(prog.uniforms['dashPeriod'], self.dashPeriod)

        colorAttrib = prog.attributes['color']
        if self.useColorVboData and self.colorVboData is not None:
            glEnableVertexAttribArray(colorAttrib)
            self.colorVboData.setVertexAttrib(colorAttrib)
        else:
            glDisableVertexAttribArray(colorAttrib)
            glVertexAttrib4f(colorAttrib, *self.color)

        distAttrib = prog.attributes['distance']
        glEnableVertexAttribArray(distAttrib)
        self.distVboData.setVertexAttrib(distAttrib)

        xPosAttrib = prog.attributes['xPos']
        glEnableVertexAttribArray(xPosAttrib)
        self.xVboData.setVertexAttrib(xPosAttrib)

        yPosAttrib = prog.attributes['yPos']
        glEnableVertexAttribArray(yPosAttrib)
        self.yVboData.setVertexAttrib(yPosAttrib)

        glLineWidth(self.width)
        glDrawArrays(GL_LINE_STRIP, 0, self.xVboData.size)

        glDisable(GL_LINE_SMOOTH)


def _distancesFromArrays(xData, yData):
    deltas = np.dstack((np.ediff1d(xData, to_begin=np.float32(0.)),
                        np.ediff1d(yData, to_begin=np.float32(0.))))[0]
    return np.cumsum(np.sqrt((deltas ** 2).sum(axis=1)))


# points ######################################################################

DIAMOND, CIRCLE, SQUARE, PLUS, X_MARKER, POINT, PIXEL = \
    'd', 'o', 's', '+', 'x', '.', ','


class _Points2D(object):
    MARKERS = DIAMOND, CIRCLE, SQUARE, PLUS, X_MARKER, POINT, PIXEL

    _LINEAR, _LOG10_X, _LOG10_Y, _LOG10_X_Y = 0, 1, 2, 3

    _SHDRS = {
        'vertexTransforms': {
            _LINEAR: """
        vec4 transformXY(float x, float y) {
            return vec4(x, y, 0.0, 1.0);
        }
        """,
            _LOG10_X: """
        const float oneOverLog10 = 0.43429448190325176;

        vec4 transformXY(float x, float y) {
            return vec4(oneOverLog10 * log(x), y, 0.0, 1.0);
        }
        """,
            _LOG10_Y: """
        const float oneOverLog10 = 0.43429448190325176;

        vec4 transformXY(float x, float y) {
            return vec4(x, oneOverLog10 * log(y), 0.0, 1.0);
        }
        """,
            _LOG10_X_Y: """
        const float oneOverLog10 = 0.43429448190325176;

        vec4 transformXY(float x, float y) {
            return vec4(oneOverLog10 * log(x),
                        oneOverLog10 * log(y),
                        0.0, 1.0);
        }
        """
        },
        'vertex': ("""
    #version 120

    uniform mat4 matrix;
    uniform int transform;
    uniform float size;
    attribute float xPos;
    attribute float yPos;
    attribute vec4 color;

    varying vec4 vColor;
    """,
                   """
    void main(void) {
        gl_Position = matrix * transformXY(xPos, yPos);
        vColor = color;
        gl_PointSize = size;
    }
    """),

        'fragmentSymbols': {
            DIAMOND: """
        float alphaSymbol(vec2 coord, float size) {
            vec2 centerCoord = abs(coord - vec2(0.5, 0.5));
            float f = centerCoord.x + centerCoord.y;
            return clamp(size * (0.5 - f), 0., 1.);
        }
        """,
            CIRCLE: """
        float alphaSymbol(vec2 coord, float size) {
            float radius = 0.5;
            float r = distance(coord, vec2(0.5, 0.5));
            return clamp(size * (radius - r), 0., 1.);
        }
        """,
            SQUARE: """
        float alphaSymbol(vec2 coord, float size) {
            return 1.;
        }
        """,
            PLUS: """
        float alphaSymbol(vec2 coord, float size) {
            vec2 d = abs(size * (coord - vec2(0.5, 0.5)));
            if (min(d.x, d.y) < 0.5) {
                return 1.;
            } else {
                return 0.;
            }
        }
        """,
            X_MARKER: """
        float alphaSymbol(vec2 coord, float size) {
            float d1 = abs(coord.x - coord.y);
            float d2 = abs(coord.x + coord.y - 1.);
            if (min(d1, d2) < 0.5/size) {
                return 1.;
            } else {
                return 0.;
            }
        }
        """
        },

        'fragment': ("""
    #version 120

    uniform float size;

    varying vec4 vColor;
    """,
                     """
    void main(void) {
        float alpha = alphaSymbol(gl_PointCoord, size);
        if (alpha <= 0.) {
            discard;
        } else {
            gl_FragColor = vec4(vColor.rgb, alpha * clamp(vColor.a, 0., 1.));
        }
    }
    """)
    }

    _programs = defaultdict(dict)

    def __init__(self, xVboData=None, yVboData=None, colorVboData=None,
                 marker=SQUARE, color=(0., 0., 0., 1.), size=7):
        self.color = color
        self.marker = marker
        self.size = size

        self.xVboData = xVboData
        self.yVboData = yVboData
        self.colorVboData = colorVboData
        self.useColorVboData = colorVboData is not None

    @property
    def marker(self):
        return self._marker

    @marker.setter
    def marker(self, marker):
        if marker in _MPL_NONES:
            self._marker = None
            self.render = self._renderNone
        else:
            assert marker in self.MARKERS
            self._marker = marker
            self.render = self._renderMarkers

    @property
    def size(self):
        return self._size

    @size.setter
    def size(self, size):
        # try:
        #    sizeRange = self._sizeRange
        # except AttributeError:
        #    sizeRange = glGetFloatv(GL_POINT_SIZE_RANGE)
        #    # Shared among contexts, this should be enough..
        #    _Points2D._sizeRange = sizeRange
        # assert size >= sizeRange[0] and size <= sizeRange[1]
        self._size = size

    @classmethod
    def _getProgram(cls, transform, marker):
        context = getGLContext()
        if marker == PIXEL:
            marker = SQUARE
        elif marker == POINT:
            marker = CIRCLE
        programs = cls._programs[(transform, marker)]
        try:
            prgm = programs[context]
        except KeyError:
            vertShdr = cls._SHDRS['vertex'][0] + \
                cls._SHDRS['vertexTransforms'][transform] + \
                cls._SHDRS['vertex'][1]
            fragShdr = cls._SHDRS['fragment'][0] + \
                cls._SHDRS['fragmentSymbols'][marker] + \
                cls._SHDRS['fragment'][1]
            prgm = Program(vertShdr, fragShdr)

            programs[context] = prgm
        return prgm

    @classmethod
    def init(cls):
        version = glGetString(GL_VERSION)
        majorVersion = int(version[0])
        assert majorVersion >= 2
        glEnable(GL_VERTEX_PROGRAM_POINT_SIZE)  # OpenGL 2
        glEnable(GL_POINT_SPRITE)  # OpenGL 2
        if majorVersion >= 3:  # OpenGL 3
            glEnable(GL_PROGRAM_POINT_SIZE)

    def _renderNone(self, matrix, isXLog, isYLog):
        pass

    render = _renderNone

    def _renderMarkers(self, matrix, isXLog, isYLog):
        if isXLog:
            transform = self._LOG10_X_Y if isYLog else self._LOG10_X
        else:
            transform = self._LOG10_Y if isYLog else self._LINEAR

        prog = self._getProgram(transform, self.marker)
        prog.use()
        glUniformMatrix4fv(prog.uniforms['matrix'], 1, GL_TRUE, matrix)
        if self.marker == PIXEL:
            size = 1
        elif self.marker == POINT:
            size = math.ceil(0.5 * self.size) + 1  # Mimic Matplotlib point
        else:
            size = self.size
        glUniform1f(prog.uniforms['size'], size)
        # glPointSize(self.size)

        cAttrib = prog.attributes['color']
        if self.useColorVboData and self.colorVboData is not None:
            glEnableVertexAttribArray(cAttrib)
            self.colorVboData.setVertexAttrib(cAttrib)
        else:
            glDisableVertexAttribArray(cAttrib)
            glVertexAttrib4f(cAttrib, *self.color)

        xAttrib = prog.attributes['xPos']
        glEnableVertexAttribArray(xAttrib)
        self.xVboData.setVertexAttrib(xAttrib)

        yAttrib = prog.attributes['yPos']
        glEnableVertexAttribArray(yAttrib)
        self.yVboData.setVertexAttrib(yAttrib)

        glDrawArrays(GL_POINTS, 0, self.xVboData.size)

        glUseProgram(0)


# curves ######################################################################

def _proxyProperty(*componentsAttributes):
    """Create a property to access an attribute of attribute(s).
    Useful for composition.
    Supports multiple components this way:
    getter returns the first found, setter sets all
    """
    def getter(self):
        for compName, attrName in componentsAttributes:
            try:
                component = getattr(self, compName)
            except AttributeError:
                pass
            else:
                return getattr(component, attrName)

    def setter(self, value):
        for compName, attrName in componentsAttributes:
            component = getattr(self, compName)
            setattr(component, attrName, value)
    return property(getter, setter)


class Curve2D(object):
    def __init__(self, xData, yData, colorData=None,
                 lineStyle=None, lineColor=None,
                 lineWidth=None, lineDashPeriod=None,
                 marker=None, markerColor=None, markerSize=None,
                 fillColor=None):
        self._isXLog = False
        self._isYLog = False
        self.xData, self.yData, self.colorData = xData, yData, colorData
        self._xDataLog, self._yDataLog, self._colorDataLog = None, None, None

        self.xMin, self.xMax = minMax(xData)
        self.yMin, self.yMax = minMax(yData)

        if fillColor is not None:
            self.fill = _Fill2D(color=fillColor)
        else:
            self.fill = None

        kwargs = {'style': lineStyle}
        if lineColor is not None:
            kwargs['color'] = lineColor
        if lineWidth is not None:
            kwargs['width'] = lineWidth
        if lineDashPeriod is not None:
            kwargs['dashPeriod'] = lineDashPeriod
        self.lines = _Lines2D(**kwargs)

        kwargs = {'marker': marker}
        if markerColor is not None:
            kwargs['color'] = markerColor
        if markerSize is not None:
            kwargs['size'] = markerSize
        self.points = _Points2D(**kwargs)

    xVboData = _proxyProperty(('lines', 'xVboData'), ('points', 'xVboData'))

    yVboData = _proxyProperty(('lines', 'yVboData'), ('points', 'yVboData'))

    colorVboData = _proxyProperty(('lines', 'colorVboData'),
                                  ('points', 'colorVboData'))

    useColorVboData = _proxyProperty(('lines', 'useColorVboData'),
                                     ('points', 'useColorVboData'))

    distVboData = _proxyProperty(('lines', 'distVboData'))

    lineStyle = _proxyProperty(('lines', 'style'))

    lineColor = _proxyProperty(('lines', 'color'))

    lineWidth = _proxyProperty(('lines', 'width'))

    lineDashPeriod = _proxyProperty(('lines', 'dashPeriod'))

    marker = _proxyProperty(('points', 'marker'))

    markerColor = _proxyProperty(('points', 'color'))

    markerSize = _proxyProperty(('points', 'size'))

    @classmethod
    def init(cls):
        _Lines2D.init()
        _Points2D.init()

    @staticmethod
    def _logFilterData(x, y, color=None, xLog=False, yLog=False):
        # Copied from Plot.py
        if xLog and yLog:
            idx = np.nonzero((x > 0) & (y > 0))[0]
            x = np.take(x, idx)
            y = np.take(y, idx)
        elif yLog:
            idx = np.nonzero(y > 0)[0]
            x = np.take(x, idx)
            y = np.take(y, idx)
        elif xLog:
            idx = np.nonzero(x > 0)[0]
            x = np.take(x, idx)
            y = np.take(y, idx)
        if isinstance(color, np.ndarray):
            colors = np.zeros((x.size, 4), color.dtype)
            colors[:, 0] = color[idx, 0]
            colors[:, 1] = color[idx, 1]
            colors[:, 2] = color[idx, 2]
            colors[:, 3] = color[idx, 3]
        else:
            colors = color
        return x, y, colors

    def prepare(self, isXLog, isYLog):
        xData, yData, color = self.xData, self.yData, self.colorData

        if self._isXLog != isXLog or self._isYLog != isYLog:
            # Log state has changed
            self._isXLog, self._isYLog = isXLog, isYLog

            # Check if data <=0. with log scale
            if (isXLog and self.xMin <= 0.) or (isYLog and self.yMin <= 0.):
                # Filtering data is needed
                xData, yData, color = self._logFilterData(
                    self.xData, self.yData, self.colorData,
                    self._isXLog, self._isYLog)

            # Update min and max (Not so correct to do it here)
            self.xMin, self.xMax = minMax(xData)
            self.yMin, self.yMax = minMax(yData)

            self.discard()

        # init once, does not support update
        if self.xVboData is None:
            xAttrib, yAttrib, cAttrib, dAttrib = None, None, None, None
            if self.lineStyle == DASHED:
                dists = _distancesFromArrays(self.xData, self.yData)
                if self.colorData is None:
                    xAttrib, yAttrib, dAttrib = createVBOFromArrays(
                        (self.xData, self.yData, dists),
                        prefix=(1, 1, 0), suffix=(1, 1, 0))
                else:
                    xAttrib, yAttrib, cAttrib, dAttrib = createVBOFromArrays(
                        (self.xData, self.yData, self.colorData, dists),
                        prefix=(1, 1, 0, 0), suffix=(1, 1, 0, 0))
            elif self.colorData is None:
                xAttrib, yAttrib = createVBOFromArrays(
                    (self.xData, self.yData),
                    prefix=(1, 1), suffix=(1, 1))
            else:
                xAttrib, yAttrib, cAttrib = createVBOFromArrays(
                    (self.xData, self.yData, self.colorData),
                    prefix=(1, 1, 0))

            # Shrink VBO
            self.xVboData = VBOAttrib(xAttrib.vbo, xAttrib.type_,
                                      xAttrib.size - 2, xAttrib.dimension,
                                      xAttrib.offset + xAttrib.itemSize,
                                      xAttrib.stride)
            self.yVboData = VBOAttrib(yAttrib.vbo, yAttrib.type_,
                                      yAttrib.size - 2, yAttrib.dimension,
                                      yAttrib.offset + yAttrib.itemSize,
                                      yAttrib.stride)
            self.colorVboData = cAttrib
            self.distVboData = dAttrib

            if self.fill is not None:
                xData = self.xData[:]
                xData.shape = xData.size, 1
                zero = np.array((1e-32,), dtype=self.yData.dtype)

                # Add one point before data: (x0, 0.)
                xAttrib.vbo.update(xData[0], xAttrib.offset,
                                   xData[0].itemsize)
                yAttrib.vbo.update(zero, yAttrib.offset, zero.itemsize)

                # Add one point after data: (xN, 0.)
                xAttrib.vbo.update(xData[-1],
                                   xAttrib.offset +
                                   (xAttrib.size - 1) * xAttrib.itemSize,
                                   xData[-1].itemsize)
                yAttrib.vbo.update(zero,
                                   yAttrib.offset +
                                   (yAttrib.size - 1) * yAttrib.itemSize,
                                   zero.itemsize)

                self.fill.xFillVboData = xAttrib
                self.fill.yFillVboData = yAttrib
                self.fill.xMin, self.fill.yMin = self.xMin, self.yMin
                self.fill.xMax, self.fill.yMax = self.xMax, self.yMax

    def render(self, matrix, isXLog, isYLog):
        self.prepare(isXLog, isYLog)
        if self.fill is not None:
            self.fill.render(matrix, isXLog, isYLog)
        self.lines.render(matrix, isXLog, isYLog)
        self.points.render(matrix, isXLog, isYLog)

    def discard(self):
        if self.xVboData is not None:
            self.xVboData.vbo.discard()

        self.xVboData = None
        self.yVboData = None
        self.colorVboData = None
        self.distVboData = None

    def pick(self, xPickMin, yPickMin, xPickMax, yPickMax):
        """Perform picking on the curve according to its rendering.

        The picking area is [xPickMin, xPickMax], [yPickMin, yPickMax].

        In case a segment between 2 points with indices i, i+1 is picked,
        only its lower index end point (i.e., i) is added to the result.
        In case an end point with index i is picked it is added to the result,
        and the segment [i-1, i] is not tested for picking.

        :return: The indices of the picked data
        :rtype: list of int
        """
        if (self.marker is None and self.lineStyle is None) or \
           self.xMin > xPickMax or xPickMin > self.xMax or \
           self.yMin > yPickMax or yPickMin > self.yMax:
            return None

        elif self.lineStyle is not None:
            # Using Cohen-Sutherland algorithm for line clipping
            codes = ((self.yData > yPickMax) << 3) | \
                    ((self.yData < yPickMin) << 2) | \
                    ((self.xData > xPickMax) << 1) | \
                    (self.xData < xPickMin)

            # Add all points that are inside the picking area
            indices = np.nonzero(codes == 0)[0].tolist()

            # Segment that might cross the area with no end point inside it
            segToTestIdx = np.nonzero((codes[:-1] != 0) &
                                      (codes[1:] != 0) &
                                      ((codes[:-1] & codes[1:]) == 0))[0]

            TOP, BOTTOM, RIGHT, LEFT = (1 << 3), (1 << 2), (1 << 1), (1 << 0)

            for index in segToTestIdx:
                if index not in indices:
                    x0, y0 = self.xData[index], self.yData[index]
                    x1, y1 = self.xData[index + 1], self.yData[index + 1]
                    code1 = codes[index + 1]

                    # check for crossing with horizontal bounds
                    # y0 == y1 is a never event:
                    # => pt0 and pt1 in same vertical area are not in segToTest
                    if code1 & TOP:
                        x = x0 + (x1 - x0) * (yPickMax - y0) / (y1 - y0)
                    elif code1 & BOTTOM:
                        x = x0 + (x1 - x0) * (yPickMin - y0) / (y1 - y0)
                    else:
                        x = None  # No horizontal bounds intersection test

                    if x is not None and x >= xPickMin and x <= xPickMax:
                        # Intersection
                        indices.append(index)

                    else:
                        # check for crossing with vertical bounds
                        # x0 == x1 is a never event (see remark for y)
                        if code1 & RIGHT:
                            y = y0 + (y1 - y0) * (xPickMax - x0) / (x1 - x0)
                        elif code1 & LEFT:
                            y = y0 + (y1 - y0) * (xPickMin - x0) / (x1 - x0)
                        else:
                            y = None  # No vertical bounds intersection test

                        if y is not None and y >= yPickMin and y <= yPickMax:
                            # Intersection
                            indices.append(index)

            indices.sort()

        else:
            indices = np.nonzero((self.xData >= xPickMin) &
                                 (self.xData <= xPickMax) &
                                 (self.yData >= yPickMin) &
                                 (self.yData <= yPickMax))[0].tolist()

        return indices


# main ########################################################################

if __name__ == "__main__":
    from OpenGL.GLUT import *  # noqa
    from .GLSupport import mat4Ortho

    glutInit(sys.argv)
    glutInitDisplayString("double rgba stencil")
    glutInitWindowSize(800, 600)
    glutInitWindowPosition(0, 0)
    glutCreateWindow('Line Plot Test')

    # GL init
    glClearColor(1., 1., 1., 1.)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    Curve2D.init()

    # Plot data init
    xData1 = np.arange(10, dtype=np.float32) * 100
    xData1[3] -= 100
    yData1 = np.asarray(np.random.random(10) * 500, dtype=np.float32)
    yData1 = np.array((100, 100, 200, 400, 100, 100, 400, 400, 401, 400),
                      dtype=np.float32)
    curve1 = Curve2D(xData1, yData1, marker='o', lineStyle='--',
                     fillColor=(1., 0., 0., 0.5))

    xData2 = np.arange(1000, dtype=np.float32) * 1
    yData2 = np.asarray(500 + np.random.random(1000) * 500, dtype=np.float32)
    curve2 = Curve2D(xData2, yData2, lineStyle='', marker='s')

    projMatrix = mat4Ortho(0, 1000, 0, 1000, -1, 1)

    def display():
        glClear(GL_COLOR_BUFFER_BIT)
        curve1.render(projMatrix, False, False)
        curve2.render(projMatrix, False, False)
        glutSwapBuffers()

    def resize(width, height):
        glViewport(0, 0, width, height)

    def idle():
        glutPostRedisplay()

    glutDisplayFunc(display)
    glutReshapeFunc(resize)
    # glutIdleFunc(idle)

    sys.exit(glutMainLoop())
