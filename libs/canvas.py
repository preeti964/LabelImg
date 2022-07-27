import numpy as np
from math import pow
from math import sqrt

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

# from PyQt4.QtOpenGL import *

from libs.shape import Shape
from libs.lib import distance
from libs.lib import distancetoline
from libs import segmentation
from libs.shape_polygon import Shape_polygon

CURSOR_DEFAULT = Qt.ArrowCursor
CURSOR_POINT = Qt.PointingHandCursor
CURSOR_DRAW = Qt.CrossCursor
CURSOR_MOVE = Qt.ClosedHandCursor
CURSOR_GRAB = Qt.OpenHandCursor


class Canvas(QWidget):
    zoomRequest = pyqtSignal(int)
    scrollRequest = pyqtSignal(int, int)
    newShape_rectbox = pyqtSignal()
    newShape_polygon = pyqtSignal()
    newShape_ellipse = pyqtSignal()
    selectionChanged = pyqtSignal(bool)
    shapeMoved = pyqtSignal()
    drawingPolygon = pyqtSignal(bool)
    # added for the polygon tool
    edgeSelected = pyqtSignal(bool, object)
    vertexSelected = pyqtSignal(bool)

    CREATE, EDIT = list(range(2))
    # polygon, rectangle,
    # _createMode = "circle"
    _createMode = "ellipse"
    _fill_drawing = False
    epsilon = 11.0

    def __init__(self, *args, **kwargs):
        self.epsilon = kwargs.pop("epsilon", 11.0)
        self.double_click = kwargs.pop("double_click", "close")
        if self.double_click not in [None, "close"]:
            raise ValueError(
                "Unexpected value for double_click event: {}".format(self.double_click)
            )
        self.num_backups = kwargs.pop("num_backups", 10)
        super(Canvas, self).__init__(*args, **kwargs)
        # Initialise local state.
        self.mode = self.EDIT
        self.shapes = []
        self.current = None
        self.shapesBackups = []
        # self.points = []
        self.selectedShape = None  # save the selected shape here
        self.selectedShapes = []  # save the selected shape here
        self.selectedShapeCopy = None
        # for polygon
        self.selectedShapesCopy = []
        self.lineColor = QColor(0, 0, 255)
        self.line = Shape(line_color=self.lineColor)
        # self.line =Shape_polygon()
        self.prevPoint = QPointF()
        self.prevMovePoint = QPointF()
        self.offsets = QPointF(), QPointF()
        self.scale = 1.0
        self.pixmap = QPixmap()
        self.visible = {}
        self._hideBackround = False
        self.hideBackround = False
        self.hShape = None
        self.hVertex = None
        # Polygon
        self.prevhVertex = None
        self.hEdge = None
        self.prevhEdge = None
        self.movingShape = False
        self._painter = QPainter()
        self._cursor = CURSOR_DEFAULT
        # Menus:
        self.menus = (QMenu(), QMenu())
        # Set widget options.
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)
        self.verified = False
        # self.segmentation = segmentation.SegmentationObject()
        self.segmentation = segmentation.SegmentationClass()
        self.is_segmenting = False
        self.include_segmentation = False
        # self.drawing_Polygon=False
        self.PolygonType = 'draw_rectbox'

    # Polygon
    def fillDrawing(self):
        return self._fill_drawing

    def setFillDrawing(self, value):
        self._fill_drawing = value

    @property
    def createMode(self):
        return self._createMode

    @createMode.setter
    def createMode(self, value):
        if value not in [
            "polygon",
            "rectangle",
            "circle",
            "line",
            "ellipse"
            "point",
            "linestrip",
        ]:
            raise ValueError("Unsupported createMode: %s" % value)
        self._createMode = value

    def storeShapes(self):
        shapesBackup = []
        for shape in self.shapes:
            shapesBackup.append(shape.copy())
        if len(self.shapesBackups) > self.num_backups:
            self.shapesBackups = self.shapesBackups[-self.num_backups - 1:]
        self.shapesBackups.append(shapesBackup)

    @property
    def isShapeRestorable(self):
        # We save the state AFTER each edit (not before) so for an
        # edit to be undoable, we expect the CURRENT and the PREVIOUS state
        # to be in the undo stack.
        if len(self.shapesBackups) < 2:
            return False
        return True

    def restoreShape(self):
        # This does _part_ of the job of restoring shapes.
        # The complete process is also done in app.py::undoShapeEdit
        # and app.py::loadShapes and our own Canvas::loadShapes function.
        if not self.isShapeRestorable:
            return
        self.shapesBackups.pop()  # latest

        # The application will eventually call Canvas.loadShapes which will
        # push this right back onto the stack.
        shapesBackup = self.shapesBackups.pop()
        self.shapes = shapesBackup
        self.selectedShapes = []
        for shape in self.shapes:
            shape.selected = False
        self.update()

    def enterEvent(self, ev):
        self.overrideCursor(self._cursor)

    def leaveEvent(self, ev):
        self.restoreCursor()

    def focusOutEvent(self, ev):
        self.restoreCursor()

    def isVisible(self, shape):
        return self.visible.get(shape, True)

    def drawing(self):
        return self.mode == self.CREATE

    def editing(self):
        return self.mode == self.EDIT

    def setEditing(self, value=True, PolygonType='draw_rectbox'):
        self.mode = self.EDIT if value else self.CREATE
        self.PolygonType = PolygonType
        if not value:  # Create
            self.unHighlight()
            self.deSelectShape()
        self.prevPoint = QPointF()
        self.repaint()

    # for polygon
    def setEditing_polygon(self, value=True, PolygonType='draw_polygon', createMode='polygon'):
        self.mode = self.EDIT if value else self.CREATE
        self.PolygonType = PolygonType
        self._createMode = createMode
        if not value:  # Create
            self.unHighlight()
            self.deSelectShape()
        self.prevPoint = QPointF()
        self.repaint()

    def unHighlight(self):
        if self.PolygonType == 'draw_rectbox':
            if self.hShape:
                self.hShape.highlightClear()
            self.hVertex = self.hShape = None
        elif self.PolygonType == 'draw_polygon':
            if self.hShape:
                self.hShape.highlightClear()
                self.update()
            self.prevhShape = self.hShape
            self.prevhVertex = self.hVertex
            self.prevhEdge = self.hEdge
            self.hShape = self.hVertex = self.hEdge = None

    def selectedVertex(self):
        return self.hVertex is not None

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        pos = self.transformPos(ev.pos())
        # Polygon drawing.
        if self.PolygonType == 'draw_rectbox':
            if self.drawing():
                self.overrideCursor(CURSOR_DRAW)
                if self.is_segmenting is True and (ev.buttons() & Qt.LeftButton):
                    self.segmentation.draw_fgmask(pos.x(), pos.y())
                    return
                if self.is_segmenting is True and (ev.buttons() & Qt.RightButton):
                    self.segmentation.draw_bgmask(pos.x(), pos.y())
                    return
                if self.current:
                    color = self.lineColor
                    if self.outOfPixmap(pos):
                        # Don't allow the user to draw outside the pixmap.
                        # Project the point to the pixmap's edges.
                        pos = self.intersectionPoint(self.current[-1], pos)
                    elif len(self.current) > 1 and self.closeEnough(pos, self.current[0]):
                        # Attract line to starting point and colorise to alert the
                        # user:
                        pos = self.current[0]
                        # print(pos)
                        color = self.current.line_color
                        self.overrideCursor(CURSOR_POINT)
                        self.current.highlightVertex(0, Shape.NEAR_VERTEX)
                    self.line[1] = pos
                    self.line.line_color = color
                    self.prevPoint = QPointF()
                    self.current.highlightClear()
                else:
                    self.prevPoint = pos
                self.repaint()
                return
            # Polygon copy moving.
            if Qt.RightButton & ev.buttons():
                if self.selectedShapeCopy and self.prevPoint:
                    self.overrideCursor(CURSOR_MOVE)
                    self.boundedMoveShape(self.selectedShapeCopy, pos)
                    self.repaint()
                elif self.selectedShape:
                    self.selectedShapeCopy = self.selectedShape.copy()
                    self.repaint()
                return

            # Polygon/Vertex moving.
            if Qt.LeftButton & ev.buttons():
                if self.selectedVertex():
                    self.boundedMoveVertex(pos)
                    self.shapeMoved.emit()
                    self.repaint()
                elif self.selectedShape and self.prevPoint:
                    self.overrideCursor(CURSOR_MOVE)
                    self.boundedMoveShape(self.selectedShape, pos)
                    self.shapeMoved.emit()
                    self.repaint()
                return

            # Just hovering over the canvas, 2 posibilities:
            # - Highlight shapes
            # - Highlight vertex
            # Update shape/vertex fill and tooltip value accordingly.
            self.setToolTip("Image")
            for shape in reversed([s for s in self.shapes if self.isVisible(s)]):
                # Look for a nearby vertex to highlight. If that fails,
                # check if we happen to be inside a shape.
                index = shape.nearestVertex(pos, self.epsilon)
                if index is not None:
                    if self.selectedVertex():
                        self.hShape.highlightClear()
                    self.hVertex, self.hShape = index, shape
                    shape.highlightVertex(index, shape.MOVE_VERTEX)
                    self.overrideCursor(CURSOR_POINT)
                    self.setToolTip("Click & drag to move point")
                    self.setStatusTip(self.toolTip())
                    self.update()
                    break
                elif shape.containsPoint(pos):
                    if self.selectedVertex():
                        self.hShape.highlightClear()
                    self.hVertex, self.hShape = None, shape
                    self.setToolTip(
                        "Click & drag to move shape '%s'" % shape.label)
                    self.setStatusTip(self.toolTip())
                    self.overrideCursor(CURSOR_GRAB)
                    self.update()
                    break
            else:  # Nothing found, clear highlights, reset state.
                if self.hShape:
                    self.hShape.highlightClear()
                    self.update()
                self.hVertex, self.hShape = None, None
                self.overrideCursor(CURSOR_DEFAULT)
        # condition for the polygon addition tool
        elif self.PolygonType == 'draw_polygon':
            self.prevMovePoint = pos
            self.restoreCursor()

            # Polygon drawing.
            if self.drawing():
                self.line.shape_type = self.createMode
                self.overrideCursor(CURSOR_DRAW)
                if not self.current:
                    return

                if self.outOfPixmap(pos):
                    # Don't allow the user to draw outside the pixmap.
                    # Project the point to the pixmap's edges.
                    pos = self.intersectionPoint(self.current[-1], pos)
                elif len(self.current) > 1 and self.createMode == "polygon" and self.closeEnough(pos, self.current[0]):
                    # Attract line to starting point and
                    # colorise to alert the user.
                    pos = self.current[0]
                    self.overrideCursor(CURSOR_POINT)
                    self.current.highlightVertex(0, Shape.NEAR_VERTEX)
                if self.createMode in ["polygon", "linestrip"]:
                    self.line[0] = self.current[-1]
                    self.line[1] = pos
                elif self.createMode == "rectangle":
                    self.line.points = [self.current[0], pos]
                    self.line.close()
                elif self.createMode == "ellipse":
                    self.line.points = [self.current[0], pos]
                    self.line.close()
                elif self.createMode == "circle":
                    self.line.points = [self.current[0], pos]
                    self.line.shape_type = "circle"
                elif self.createMode == "line":
                    self.line.points = [self.current[0], pos]
                    self.line.close()
                elif self.createMode == "point":
                    self.line.points = [self.current[0]]
                    self.line.close()
                self.repaint()
                self.current.highlightClear()
                return

            # Polygon copy moving.
            if Qt.RightButton & ev.buttons():
                if self.selectedShapeCopy and self.prevPoint:
                    self.overrideCursor(CURSOR_MOVE)
                    self.boundedMoveShape(self.selectedShapeCopy, pos)
                    self.repaint()
                elif self.selectedShape:
                    self.selectedShapeCopy = self.selectedShape.copy()
                    self.repaint()
                return

            # Polygon/Vertex moving.
            if Qt.LeftButton & ev.buttons():
                if self.selectedVertex():
                    self.boundedMoveVertex(pos)
                    self.shapeMoved.emit()
                    self.repaint()
                elif self.selectedShape and self.prevPoint:
                    self.overrideCursor(CURSOR_MOVE)
                    self.boundedMoveShape(self.selectedShape, pos)
                    self.shapeMoved.emit()
                    self.repaint()
                return

            # Just hovering over the canvas, 2 possibilities:
            # - Highlight shapes
            # - Highlight vertex
            # Update shape/vertex fill and tooltip value accordingly.
            self.setToolTip(self.tr("Image"))
            for shape in reversed([s for s in self.shapes if self.isVisible(s)]):
                # Look for a nearby vertex to highlight. If that fails,
                # check if we happen to be inside a shape.
                index = shape.nearestVertex(pos, self.epsilon / self.scale)
                # index_edge = shape.nearestEdge(pos, self.epsilon / self.scale)
                if index is not None:
                    if self.selectedVertex():
                        self.hShape.highlightClear()
                    self.prevhVertex = self.hVertex = index
                    self.prevhShape = self.hShape = shape
                    # self.prevhEdge = self.hEdge = index_edge
                    self.prevhEdge = self.hEdge
                    shape.highlightVertex(index, shape.MOVE_VERTEX)
                    self.overrideCursor(CURSOR_POINT)
                    self.setToolTip(self.tr("Click & drag to move point"))
                    self.setStatusTip(self.toolTip())
                    self.update()
                    break
                elif shape.containsPoint(pos):
                    if self.selectedVertex():
                        self.hShape.highlightClear()
                    self.prevhVertex = self.hVertex
                    self.hVertex = None
                    self.prevhShape = self.hShape = shape
                    # self.prevhEdge = self.hEdge = index_edge
                    self.prevhEdge = self.hEdge
                    self.setToolTip(
                        self.tr("Click & drag to move shape '%s'") % shape.label
                    )
                    self.setStatusTip(self.toolTip())
                    self.overrideCursor(CURSOR_GRAB)
                    self.update()
                    break

            else:  # Nothing found, clear highlights, reset state.
                self.unHighlight()
            self.edgeSelected.emit(self.hEdge is not None, self.hShape)
            self.vertexSelected.emit(self.hVertex is not None)

    def addPointToEdge(self):
        shape = self.prevhShape
        index = self.prevhEdge
        point = self.prevMovePoint
        if shape is None or index is None or point is None:
            return
        shape.insertPoint(index, point)
        shape.highlightVertex(index, shape.MOVE_VERTEX)
        self.hShape = shape
        self.hVertex = index
        self.hEdge = None
        self.movingShape = True

    def removeSelectedPoint(self):
        shape = self.prevhShape
        point = self.prevMovePoint
        if shape is None or point is None:
            return
        index = shape.nearestVertex(point, self.epsilon)
        shape.removePoint(index)
        # shape.highlightVertex(index, shape.MOVE_VERTEX)
        self.hShape = shape
        self.hVertex = None
        self.hEdge = None
        self.movingShape = True  # Save changes

    def mousePressEvent(self, ev):
        pos = self.transformPos(ev.pos())
        if self.PolygonType == 'draw_rectbox':
            if ev.button() == Qt.LeftButton:

                if self.drawing():
                    if self.is_segmenting is False:
                        self.handleDrawing(pos)
                else:
                    group_mode = int(ev.modifiers()) == Qt.ControlModifier
                    self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                    self.prevPoint = pos
                    self.repaint()

            elif ev.button() == Qt.RightButton and self.editing():
                group_mode = int(ev.modifiers()) == Qt.ControlModifier
                self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                self.prevPoint = pos
                self.repaint()
        elif self.PolygonType == 'draw_polygon':
            if ev.button() == Qt.LeftButton:
                if self.drawing():
                    if self.current:
                        # Add point to existing shape.
                        if self.createMode == "polygon":
                            self.current.addPoint(self.line[1])
                            self.line[0] = self.current[-1]
                            if self.current.isClosed():
                                self.finalise()
                        elif self.createMode in ["rectangle", "ellipse", "circle", "line"]:
                            assert len(self.current.points) == 1
                            self.current.points = self.line.points
                            self.finalise()
                        elif self.createMode == "linestrip":
                            self.current.addPoint(self.line[1])
                            self.line[0] = self.current[-1]
                            if int(ev.modifiers()) == Qt.ControlModifier:
                                self.finalise()
                    elif not self.outOfPixmap(pos):
                        # Create new shape.
                        self.current = Shape_polygon(shape_type=self.createMode)
                        self.current.addPoint(pos)
                        if self.createMode == "point":
                            self.finalise()
                        else:
                            if self.createMode == "circle":
                                self.current.shape_type = "circle"
                            self.line.points = [pos, pos]
                            self.setHiding()
                            self.drawingPolygon.emit(True)
                            self.update()
                else:
                    group_mode = int(ev.modifiers()) == Qt.ControlModifier
                    self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                    self.prevPoint = pos
                    self.repaint()
            elif ev.button() == Qt.RightButton and self.editing():
                group_mode = int(ev.modifiers()) == Qt.ControlModifier
                self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                self.prevPoint = pos
                self.repaint()

    def mouseReleaseEvent(self, ev):
        if self.PolygonType == 'draw_rectbox':
            if ev.button() == Qt.RightButton:
                if self.drawing() and self.is_segmenting is True:
                    self.segmentation.create_mask()
                    self.repaint()
                    return

                menu = self.menus[bool(self.selectedShapeCopy)]
                self.restoreCursor()
                if not menu.exec_(self.mapToGlobal(ev.pos())) \
                        and self.selectedShapeCopy:
                    # Cancel the move by deleting the shadow copy.
                    self.selectedShapeCopy = None
                    self.repaint()
            elif ev.button() == Qt.LeftButton and self.selectedShape:
                if self.selectedVertex():
                    self.overrideCursor(CURSOR_POINT)
                else:
                    self.overrideCursor(CURSOR_GRAB)
            elif ev.button() == Qt.LeftButton:
                pos = self.transformPos(ev.pos())
                if self.drawing():
                    if self.is_segmenting is False:
                        self.handleDrawing(pos)
                        return
                    if self.include_segmentation and self.is_segmenting is True:
                        self.segmentation.create_mask()
                        self.repaint()
        elif self.PolygonType == 'draw_polygon':
            if ev.button() == Qt.RightButton:
                menu = self.menus[bool(self.selectedShapeCopy)]
                self.restoreCursor()
                if not menu.exec_(self.mapToGlobal(ev.pos())) \
                        and self.selectedShapeCopy:
                    # Cancel the move by deleting the shadow copy.
                    self.selectedShapeCopy = None
                    self.repaint()
            elif ev.button() == Qt.LeftButton and self.selectedShape:
                self.overrideCursor(CURSOR_GRAB)
                if self.editing() and int(ev.modifiers()) == Qt.ShiftModifier:
                    # Add point to line if: left-click + SHIFT on a line segment
                    self.addPointToEdge()
            elif ev.button() == Qt.LeftButton and self.selectedVertex():
                if self.editing() and int(ev.modifiers()) == Qt.ShiftModifier:
                    # Delete point if: left-click + SHIFT on a point
                    self.removeSelectedPoint()

            if self.movingShape and self.hShape:
                index = self.shapes.index(self.hShape)
                if self.shapesBackups[-1][index].points != self.shapes[index].points:
                    self.storeShapes()
                    self.shapeMoved.emit()
                self.movingShape = False

    def endMove(self, copy=False):
        if self.PolygonType == 'draw_rectbox':
            assert self.selectedShape and self.selectedShapeCopy
            shape = self.selectedShapeCopy
            if copy:
                self.shapes.append(shape)
                self.selectedShape.selected = False
                self.selectedShape = shape
                self.repaint()
            else:
                self.selectedShape.points = [p for p in shape.points]
            self.selectedShapeCopy = None
        elif self.PolygonType == 'draw_polygon':
            assert self.selectedShapes and self.selectedShapesCopy
            assert len(self.selectedShapesCopy) == len(self.selectedShapes)
            if copy:
                for i, shape in enumerate(self.selectedShapesCopy):
                    self.shapes.append(shape)
                    self.selectedShapes[i].selected = False
                    self.selectedShapes[i] = shape
            else:
                for i, shape in enumerate(self.selectedShapesCopy):
                    self.selectedShapes[i].points = shape.points
            self.selectedShapesCopy = []
            self.repaint()
            self.storeShapes()
            return True

    def hideBackroundShapes(self, value):
        self.hideBackround = value
        if self.selectedShape:
            # Only hide other shapes if there is a current selection.
            # Otherwise the user will not be able to select a shape.
            self.setHiding(True)
            self.repaint()

    def handleDrawing(self, pos):
        if self.current and self.current.reachMaxPoints() is False:
            initPos = self.current[0]
            minX = initPos.x()
            minY = initPos.y()
            targetPos = self.line[1]
            maxX = targetPos.x()
            maxY = targetPos.y()
            self.current.addPoint(QPointF(maxX, minY))
            self.current.addPoint(targetPos)
            self.current.addPoint(QPointF(minX, maxY))
            self.finalise()
        elif not self.outOfPixmap(pos):
            self.current = Shape()
            self.current.addPoint(pos)
            self.line.points = [pos, pos]
            self.setHiding()
            self.drawingPolygon.emit(True)
            self.update()

    def setHiding(self, enable=True):
        self._hideBackround = self.hideBackround if enable else False

    def canCloseShape(self):
        return self.drawing() and self.current and len(self.current) > 2

    def mouseDoubleClickEvent(self, ev):
        # We need at least 4 points here, since the mousePress handler
        # adds an extra one before this handler is called.
        if self.canCloseShape() and len(self.current) > 3:
            self.current.popPoint()
            self.finalise()

    def selectShape(self, shape):
        if self.PolygonType == 'draw_rectbox':
            self.deSelectShape()
            shape.selected = True
            self.selectedShape = shape
            self.setHiding()
            self.selectionChanged.emit(True)
            self.update()
        elif self.PolygonType == 'draw_polygon':
            self.deSelectShape()
            shape.selected = True
            self.selectedShape = shape
            self.setHiding()
            self.selectionChanged.emit(True)
            self.update()

    def selectShapePoint(self, point, multiple_selection_mode):
        if self.PolygonType == 'draw_rectbox':
            """Select the first shape created which contains this point."""
            self.deSelectShape()
            if self.selectedVertex():  # A vertex is marked for selection.
                index, shape = self.hVertex, self.hShape
                shape.highlightVertex(index, shape.MOVE_VERTEX)
                self.selectShape(shape)
                return
            for shape in reversed(self.shapes):
                if self.isVisible(shape) and shape.containsPoint(point):
                    self.selectShape(shape)
                    self.calculateOffsets(shape, point)
                    return
        elif self.PolygonType == 'draw_polygon':
            """Select the first shape created which contains this point."""
            self.deSelectShape()
            if self.selectedVertex():  # A vertex is marked for selection.
                index, shape = self.hVertex, self.hShape
                shape.highlightVertex(index, shape.MOVE_VERTEX)
                self.selectShape(shape)
                return
            for shape in reversed(self.shapes):
                if self.isVisible(shape) and shape.containsPoint(point):
                    self.selectShape(shape)
                    self.calculateOffsets(shape, point)
                    return

    def calculateOffsets(self, shape, point):
        rect = shape.boundingRect()
        x1 = rect.x() - point.x()
        y1 = rect.y() - point.y()
        x2 = (rect.x() + rect.width()) - point.x()
        y2 = (rect.y() + rect.height()) - point.y()
        self.offsets = QPointF(x1, y1), QPointF(x2, y2)

    def boundedMoveVertex(self, pos):
        if self.PolygonType == 'draw_rectbox':
            index, shape = self.hVertex, self.hShape
            point = shape[index]
            if self.outOfPixmap(pos):
                pos = self.intersectionPoint(point, pos)
            shiftPos = pos - point
            shape.moveVertexBy(index, shiftPos)
            lindex = (index + 1) % 4
            rindex = (index + 3) % 4
            lshift = None
            rshift = None
            if index % 2 == 0:
                rshift = QPointF(shiftPos.x(), 0)
                lshift = QPointF(0, shiftPos.y())
            else:
                lshift = QPointF(shiftPos.x(), 0)
                rshift = QPointF(0, shiftPos.y())
            shape.moveVertexBy(rindex, rshift)
            shape.moveVertexBy(lindex, lshift)
        elif self.PolygonType == 'draw_polygon':
            index, shape = self.hVertex, self.hShape
            point = shape[index]
            if self.outOfPixmap(pos):
                pos = self.intersectionPoint(point, pos)
            shape.moveVertexBy(index, pos - point)

    def boundedMoveShape(self, shape, pos):
        if self.outOfPixmap(pos):
            return False  # No need to move
        o1 = pos + self.offsets[0]
        if self.outOfPixmap(o1):
            pos -= QPointF(min(0, o1.x()), min(0, o1.y()))
        o2 = pos + self.offsets[1]
        if self.outOfPixmap(o2):
            pos += QPointF(min(0, self.pixmap.width() - o2.x()),
                           min(0, self.pixmap.height() - o2.y()))
        # The next line tracks the new position of the cursor
        # relative to the shape, but also results in making it
        # a bit "shaky" when nearing the border and allows it to
        # go outside of the shape's area for some reason. XXX
        dp = pos - self.prevPoint
        if dp:
            shape.moveBy(dp)
            self.prevPoint = pos
            return True
        return False

    def deSelectShape(self):
        if self.PolygonType == 'draw_rectbox':
            if self.selectedShape:
                self.selectedShape.selected = False
                self.selectedShape = None
                self.setHiding(False)
                self.selectionChanged.emit(False)
                self.update()
        elif self.PolygonType == 'draw_polygon':
            if self.selectedShape:
                self.selectedShape.selected = False
                self.selectedShape = None
                self.setHiding(False)
                self.selectionChanged.emit(False)
                self.update()

    def deleteSelected(self):
        if self.PolygonType == 'draw_rectbox':
            if self.selectedShape:
                shape = self.selectedShape
                self.shapes.remove(self.selectedShape)
                self.selectedShape = None
                self.update()
                return shape
        elif self.PolygonType == 'draw_polygon':
            if self.selectedShape:
                shape = self.selectedShape
                self.shapes.remove(self.selectedShape)
                self.selectedShape = None
                self.update()
                return shape

    def deleteShape(self, shape):
        if shape in self.selectedShapes:
            self.selectedShapes.remove(shape)
        if shape in self.shapes:
            self.shapes.remove(shape)
        self.storeShapes()
        self.update()

    def copySelectedShape(self):
        if self.PolygonType == 'draw_rectbox':
            if self.selectedShape:
                shape = self.selectedShape.copy()
                self.deSelectShape()
                self.shapes.append(shape)
                shape.selected = True
                self.selectedShape = shape
                self.boundedShiftShape(shape)
                return shape
        elif self.PolygonType == 'draw_polygon':
            if self.selectedShape:
                shape = self.selectedShape.copy()
                self.deSelectShape()
                self.shapes.append(shape)
                shape.selected = True
                self.selectedShape = shape
                self.boundedShiftShape(shape)
                return shape
            # if self.selectedShape:
            #     self.selectedShapeCopy = [s.copy() for s in self.selectedShape]
            #     self.boundedShiftShapes(self.selectedShapesCopy)
            #     self.endMove(copy=True)
            # return self.selectedShapes

    def boundedShiftShape(self, shape):
        # Try to move in one direction, and if it fails in another.
        # Give up if both fail.
        point = shape[0]
        offset = QPointF(2.0, 2.0)
        self.calculateOffsets(shape, point)
        self.prevPoint = point
        if not self.boundedMoveShape(shape, point - offset):
            self.boundedMoveShape(shape, point + offset)

    def paintEvent(self, event):
        if self.PolygonType == 'draw_rectbox':
            if not self.pixmap:
                return super(Canvas, self).paintEvent(event)

            p = self._painter
            p.begin(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.HighQualityAntialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)

            p.scale(self.scale, self.scale)
            p.translate(self.offsetToCenter())

            p.drawPixmap(0, 0, self.pixmap)
            Shape.scale = self.scale
            for shape in self.shapes:
                if (shape.selected or not self._hideBackround) and self.isVisible(shape):
                    shape.fill = shape.selected or shape == self.hShape
                    shape.paint(p)

            if self.current:
                self.current.paint(p)
                self.line.paint(p)
            if self.selectedShapeCopy:
                self.selectedShapeCopy.paint(p)

            # Paint rect
            if self.current is not None and len(self.line) == 2:
                leftTop = self.line[0]
                rightBottom = self.line[1]
                rectWidth = rightBottom.x() - leftTop.x()
                rectHeight = rightBottom.y() - leftTop.y()
                color = QColor(0, 220, 0)
                p.setPen(color)
                brush = QBrush(Qt.BDiagPattern)
                p.setBrush(brush)
                p.drawRect(leftTop.x(), leftTop.y(), rectWidth, rectHeight)
            if self.drawing() and not self.prevPoint.isNull() and not self.outOfPixmap(self.prevPoint):
                p.setPen(QColor(0, 0, 0))
                p.drawLine(self.prevPoint.x(), 0, self.prevPoint.x(), self.pixmap.height())
                p.drawLine(0, self.prevPoint.y(), self.pixmap.width(), self.prevPoint.y())

            current_segment = self.segmentation.get_current_segment()
            if current_segment is not None:
                p.setPen(QColor(0, 0, 255))
                for segment in current_segment:
                    for point in segment:
                        x, y = point[0]
                        p.drawPoint(x, y)

            if self.include_segmentation:
                all_segments = self.segmentation.get_all_segments()
                if all_segments is not None:
                    p.setPen(QColor(255, 0, 0))
                    for _, segment in all_segments.items():
                        for contour in segment:
                            for point in contour:
                                x, y = point[0]
                                p.drawPoint(x, y)
            self.setAutoFillBackground(True)
            if self.verified:
                pal = self.palette()
                pal.setColor(self.backgroundRole(), QColor(184, 239, 38, 128))
                self.setPalette(pal)
            else:
                pal = self.palette()
                pal.setColor(self.backgroundRole(), QColor(232, 232, 232, 255))
                self.setPalette(pal)
            p.end()

        elif self.PolygonType == 'draw_polygon':
            if not self.pixmap:
                return super(Canvas, self).paintEvent(event)

            p = self._painter
            p.begin(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.HighQualityAntialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)

            p.scale(self.scale, self.scale)
            p.translate(self.offsetToCenter())

            p.drawPixmap(0, 0, self.pixmap)
            Shape.scale = self.scale
            for shape in self.shapes:
                if (shape.selected or not self._hideBackround) and self.isVisible(shape):
                    shape.fill = shape.selected or shape == self.hShape
                    shape.paint(p)
            if self.current:
                self.current.paint(p)
                self.line.paint(p)
            if self.selectedShapeCopy:
                for s in self.selectedShapeCopy:
                    s.paint(p)

            if self.fillDrawing() and self.createMode == "polygon" and self.current is not None and len(self.current.points) >= 2:
                drawing_shape = self.current.copy()
                drawing_shape.addPoint(self.line[1])
                drawing_shape.fill = True
                drawing_shape.paint(p)

            current_segment = self.segmentation.get_current_segment()
            if current_segment is not None:
                p.setPen(QColor(0, 0, 255))
                for segment in current_segment:
                    for point in segment:
                        x, y = point[0]
                        p.drawPoint(x, y)

            if self.include_segmentation:
                all_segments = self.segmentation.get_all_segments()
                if all_segments is not None:
                    p.setPen(QColor(255, 0, 0))
                    for _, segment in all_segments.items():
                        for contour in segment:
                            for point in contour:
                                x, y = point[0]
                                p.drawPoint(x, y)

            self.setAutoFillBackground(True)
            if self.verified:
                pal = self.palette()
                pal.setColor(self.backgroundRole(), QColor(184, 239, 38, 128))
                self.setPalette(pal)
            else:
                pal = self.palette()
                pal.setColor(self.backgroundRole(), QColor(232, 232, 232, 255))
                self.setPalette(pal)
            p.end()

    def transformPos(self, point):
        """Convert from widget-logical coordinates to painter-logical coordinates."""
        return point / self.scale - self.offsetToCenter()

    def offsetToCenter(self):
        s = self.scale
        area = super(Canvas, self).size()
        w, h = self.pixmap.width() * s, self.pixmap.height() * s
        aw, ah = area.width(), area.height()
        x = (aw - w) / (2 * s) if aw > w else 0
        y = (ah - h) / (2 * s) if ah > h else 0
        return QPointF(x, y)

    def outOfPixmap(self, p):
        w, h = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= w and 0 <= p.y() <= h)

    def finalise(self):
        if self.PolygonType == 'draw_rectbox':
            def start_segmenting():
                if self.current is not None:
                    xi, yi = self.current[0].x(), self.current[0].y()
                    xj, yj = self.current[2].x(), self.current[2].y()
                    minX, minY = min(xi, xj), min(yi, yj)
                    maxX, maxY = max(xi, xj), max(yi, yj)

                    rect = (int(minX),
                            int(minY),
                            int(maxX - minX),
                            int(maxY - minY))
                    self.segmentation.create_mask(rect=rect, init_with_rect=True)
                    self.is_segmenting = True
                # if self.current is not None:
                #     x1, y1 = self.current[0].x(), self.current[0].y()
                #     x2, y2 = self.current[1].x(), self.current[1].y()
                #     x3, y3 = self.current[2].x(), self.current[2].y()
                #     x4, y4 = self.current[3].x(), self.current[3].y()
                #     # minX, minY = min(xi, xj), min(yi, yj)
                #     # maxX, maxY = max(xi, xj), max(yi, yj)
                #     #
                #     # rect = (int(minX),
                #     #         int(minY),
                #     #         int(maxX - minX),
                #     #         int(maxY - minY))
                #     # print(self.current.points)
                #     # # self.segmentation.create_mask(rect=rect, init_with_rect=True)
                #
                #     rect_point = np.array([[x1,y1],[x2,y2],[x3,y3],[x4,y4]],dtype=np.int32)
                #     self.segmentation.create_poly_mask(rect=rect_point)
                #     self.is_segmenting = True

            assert self.current
            if self.current.points[0] == self.current.points[-1]:
                self.current = None
                self.drawingPolygon.emit(False)
                self.update()
                return

            self.current.close()
            self.shapes.append(self.current)
            self.setHiding(False)
            self.newShape_rectbox.emit()
            if self.include_segmentation and self.is_segmenting is False:
                start_segmenting()
            self.current = None
            self.update()
        elif self.PolygonType == 'draw_polygon':
            def start_segmenting():
                if self.createMode == 'polygon':
                    if self.current is not None:
                        x_value = []
                        y_value = []
                        point = []
                        j = 0
                        for i in self.current.points:
                            x = self.current[j].x()
                            y = self.current[j].y()
                            point.append(i)
                            x_value.append(int(x))
                            y_value.append(int(y))
                            print(i)
                            j = j + 1
                        merged_list = [(x_value[i], y_value[i]) for i in range(0, len(x_value))]
                        points = np.asarray([merged_list], dtype=np.int32)
                        self.segmentation.create_poly_mask(rect=points)
                        self.is_segmenting = True
                elif self.createMode == 'circle':
                    if self.current is not None:
                        xi, yi = self.current[0].x(), self.current[0].y()
                        xj, yj = self.current[1].x(), self.current[1].y()
                        X, Y = (xi - xj), (yi - yj)
                        r = sqrt(pow(X, 2) + pow(Y, 2))
                        self.segmentation.create_cir_mask(int(xi), int(yi), int(r))
                        self.is_segmenting = True
                elif self.createMode == 'ellipse':
                    xi, yi = self.current[0].x(), self.current[0].y()
                    xj, yj = self.current[1].x(), self.current[1].y()
                    minX, minY = min(xi, xj), min(yi, yj)
                    maxX, maxY = max(xi, xj), max(yi, yj)
                    elps_shape = [(minX, minY), (maxX, maxY)]
                    self.segmentation.create_ellipse_mask(elps_shape)
                    self.is_segmenting = True

            assert self.current
            self.current.close()
            self.shapes.append(self.current)
            self.storeShapes()
            self.setHiding(False)
            if self.createMode == 'polygon':
                self.newShape_polygon.emit()
            elif self.createMode == 'ellipse':
                self.newShape_ellipse.emit()
            if self.include_segmentation and self.is_segmenting is False:
                start_segmenting()
            self.current = None
            self.update()

    def closeEnough(self, p1, p2):
        # d = distance(p1 - p2)
        # m = (p1-p2).manhattanLength()
        # print "d %.2f, m %d, %.2f" % (d, m, d - m)
        return distance(p1 - p2) < self.epsilon

    def intersectionPoint(self, p1, p2):
        # Cycle through each image edge in clockwise fashion,
        # and find the one intersecting the current line segment.
        # http://paulbourke.net/geometry/lineline2d/
        size = self.pixmap.size()
        points = [(0, 0),
                  (size.width(), 0),
                  (size.width(), size.height()),
                  (0, size.height())]
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        d, i, (x, y) = min(self.intersectingEdges((x1, y1), (x2, y2), points))
        x3, y3 = points[i]
        x4, y4 = points[(i + 1) % 4]
        if (x, y) == (x1, y1):
            # Handle cases where previous point is on one of the edges.
            if x3 == x4:
                return QPointF(x3, min(max(0, y2), max(y3, y4)))
            else:
                return QPointF(min(max(0, x2), max(x3, x4)), y3)
        return QPointF(x, y)

    def intersectingEdges(self, x1y1, x2y2, points):
        """For each edge formed by `points', yield the intersection
        with the line segment `(x1,y1) - (x2,y2)`, if it exists.
        Also return the distance of `(x2,y2)' to the middle of the
        edge along with its index, so that the one closest can be chosen."""
        x1, y1 = x1y1
        x2, y2 = x2y2
        for i in range(4):
            x3, y3 = points[i]
            x4, y4 = points[(i + 1) % 4]
            denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
            nua = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
            nub = (x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)
            if denom == 0:
                # This covers two cases:
                #   nua == nub == 0: Coincident
                #   otherwise: Parallel
                continue
            ua, ub = nua / denom, nub / denom
            if 0 <= ua <= 1 and 0 <= ub <= 1:
                x = x1 + ua * (x2 - x1)
                y = y1 + ua * (y2 - y1)
                m = QPointF((x3 + x4) / 2, (y3 + y4) / 2)
                d = distance(m - QPointF(x2, y2))
                yield d, i, (x, y)

    # These two, along with a call to adjustSize are required for the
    # scroll area.
    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        if self.pixmap:
            return self.scale * self.pixmap.size()
        return super(Canvas, self).minimumSizeHint()

    def wheelEvent(self, ev):
        qt_version = 4 if hasattr(ev, "delta") else 5
        if qt_version == 4:
            if ev.orientation() == Qt.Vertical:
                v_delta = ev.delta()
                h_delta = 0
            else:
                h_delta = ev.delta()
                v_delta = 0
        else:
            delta = ev.angleDelta()
            h_delta = delta.x()
            v_delta = delta.y()
        mods = ev.modifiers()
        if Qt.ControlModifier == int(mods) and v_delta:
            self.zoomRequest.emit(v_delta)
        else:
            v_delta and self.scrollRequest.emit(v_delta, Qt.Vertical)
            h_delta and self.scrollRequest.emit(h_delta, Qt.Horizontal)
        ev.accept()

    def keyPressEvent(self, ev):
        key = ev.key()
        if key == Qt.Key_Escape and self.current:
            print('ESC press')
            self.current = None
            self.drawingPolygon.emit(False)
            self.update()
        elif key == Qt.Key_Return and self.canCloseShape():
            self.finalise()
        elif key == Qt.Key_Left and self.selectedShape:
            self.moveOnePixel('Left')
        elif key == Qt.Key_Right and self.selectedShape:
            self.moveOnePixel('Right')
        elif key == Qt.Key_Up and self.selectedShape:
            self.moveOnePixel('Up')
        elif key == Qt.Key_Down and self.selectedShape:
            self.moveOnePixel('Down')

    def moveOnePixel(self, direction):
        if direction == 'Left' and not self.moveOutOfBound(QPointF(-1.0, 0)):
            # print("move Left one pixel")
            self.selectedShape.points[0] += QPointF(-1.0, 0)
            self.selectedShape.points[1] += QPointF(-1.0, 0)
            self.selectedShape.points[2] += QPointF(-1.0, 0)
            self.selectedShape.points[3] += QPointF(-1.0, 0)
        elif direction == 'Right' and not self.moveOutOfBound(QPointF(1.0, 0)):
            # print("move Right one pixel")
            self.selectedShape.points[0] += QPointF(1.0, 0)
            self.selectedShape.points[1] += QPointF(1.0, 0)
            self.selectedShape.points[2] += QPointF(1.0, 0)
            self.selectedShape.points[3] += QPointF(1.0, 0)
        elif direction == 'Up' and not self.moveOutOfBound(QPointF(0, -1.0)):
            # print("move Up one pixel")
            self.selectedShape.points[0] += QPointF(0, -1.0)
            self.selectedShape.points[1] += QPointF(0, -1.0)
            self.selectedShape.points[2] += QPointF(0, -1.0)
            self.selectedShape.points[3] += QPointF(0, -1.0)
        elif direction == 'Down' and not self.moveOutOfBound(QPointF(0, 1.0)):
            # print("move Down one pixel")
            self.selectedShape.points[0] += QPointF(0, 1.0)
            self.selectedShape.points[1] += QPointF(0, 1.0)
            self.selectedShape.points[2] += QPointF(0, 1.0)
            self.selectedShape.points[3] += QPointF(0, 1.0)
        self.shapeMoved.emit()
        self.repaint()

    def moveOutOfBound(self, step):
        points = [p1 + p2 for p1, p2 in zip(self.selectedShape.points, [step] * 4)]
        return True in map(self.outOfPixmap, points)

    def setLastLabel(self, text):
        if self.PolygonType == 'draw_rectbox':
            assert text
            self.shapes[-1].label = text
            return self.shapes[-1]
        elif self.PolygonType == 'draw_polygon':
            assert text
            self.shapes[-1].label = text
            self.shapesBackups.pop()
            self.storeShapes()
            return self.shapes[-1]

    def endSegmenting(self, label=None):
        if self.PolygonType == 'draw_rectbox':
            if self.is_segmenting:
                self.segmentation.freeze_segment(label)
                self.setClean()
                self.repaint()
        elif self.PolygonType == 'draw_polygon':
            if self.is_segmenting:
                self.segmentation.freeze_segment(label)
                self.setClean()
                self.repaint()

    def setClean(self):
        self.is_segmenting = False

    def undoLastLine(self):
        if self.PolygonType == 'draw_rectbox':
            assert self.shapes
            self.current = self.shapes.pop()
            self.current.setOpen()
            self.line.points = [self.current[-1], self.current[0]]
            self.drawingPolygon.emit(True)
        elif self.PolygonType == 'draw_polygon':
            assert self.shapes
            self.current = self.shapes.pop()
            self.current.setOpen()
            if self.createMode in ["polygon", "linestrip"]:
                self.line.points = [self.current[-1], self.current[0]]
            elif self.createMode in ["rectangle", "ellipse", "line", "circle"]:
                self.current.points = self.current.points[0:1]
            elif self.createMode == "point":
                self.current = None
            self.drawingPolygon.emit(True)

    def resetAllLines(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.setOpen()
        self.line.points = [self.current[-1], self.current[0]]
        self.drawingPolygon.emit(True)
        self.current = None
        self.drawingPolygon.emit(False)
        self.update()

    def loadPixmap(self, pixmap):
        self.segmentation.update(pixmap)
        self.pixmap = pixmap
        self.shapes = []
        self.repaint()

    def load_seg(self, seg_path, label_path=None):
        self.segmentation.load_seg(seg_path)
        self.segmentation.load_seg_label(label_path)

    def save_seg(self, seg_path):
        if self.include_segmentation:
            self.setClean()
            self.segmentation.save_seg(seg_path)

    def loadShapes(self, shapes, replace=True):
        if self.PolygonType == 'draw_rectbox':
            self.shapes = list(shapes)
            self.current = None
            self.repaint()
        elif self.PolygonType == 'draw_polygon':
            if replace:
                self.shapes = list(shapes)
            else:
                self.shapes.extend(shapes)
            self.storeShapes()
            self.current = None
            self.hShape = None
            self.hVertex = None
            self.hEdge = None
            self.update()

    def setShapeVisible(self, shape, value):
        self.visible[shape] = value
        self.repaint()

    def currentCursor(self):
        cursor = QApplication.overrideCursor()
        if cursor is not None:
            cursor = cursor.shape()
        return cursor

    def overrideCursor(self, cursor):
        if self.PolygonType == 'draw_rectbox':
            self._cursor = cursor
            if self.currentCursor() is None:
                QApplication.setOverrideCursor(cursor)
            else:
                QApplication.changeOverrideCursor(cursor)
        elif self.PolygonType == 'draw_polygon':
            # self.restoreCursor()
            # self._cursor = cursor
            # QApplication.setOverrideCursor(cursor)
            self._cursor = cursor
            if self.currentCursor() is None:
                QApplication.setOverrideCursor(cursor)
            else:
                QApplication.changeOverrideCursor(cursor)

    def restoreCursor(self):
        QApplication.restoreOverrideCursor()

    def resetState(self):
        if self.PolygonType == 'draw_rectbox':
            self.restoreCursor()
            self.pixmap = None
            self.update()
        elif self.PolygonType == 'draw_polygon':
            self.restoreCursor()
            self.pixmap = None
            self.shapesBackups = []
            self.update()
