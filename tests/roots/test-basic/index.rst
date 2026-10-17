Java Examples
=============

.. java:package:: com.example.shapes

.. java:import:: java.util List

.. java:import:: org.javatuples Pair

.. java:type:: public interface Shape extends Comparable<Shape>

   A shape with an area.

   .. java:method:: double getArea()

      :return: The area, in square meters.

.. java:type:: public abstract class Polygon<P extends Point> implements Shape

   A shape with straight sides.

   :param P: The type of the vertices.

   .. java:field:: public static final int MAX_SIDES = 100

   .. java:field:: protected List<P> vertices

   .. java:constructor:: public Polygon(List<P> vertices)

      :param vertices: The vertices, in order.
      :throws IllegalArgumentException: If there are more than :java:field:`MAX_SIDES` vertices.

   .. java:method:: public <S extends Shape> boolean contains(S shape)

      :param S shape: The shape.
      :return: Whether the polygon contains the shape.

   .. java:method:: public Pair<P, P> getBounds()

   .. java:method:: public static Polygon<Point> of(Point... points)

.. java:type:: public class Point

   .. java:method:: public double[] getCoordinates()

.. java:type:: public enum Color implements java.io.Serializable

.. java:type:: public @interface Generated

.. java:method:: public static void draw(Shape shape)
   :outertype: Canvas

References
----------

* :java:type:`Shape`, :java:type:`~com.example.shapes.Polygon`,
  :java:meth:`Polygon.contains(S)`, :java:construct:`Polygon(List)`, :java:field:`Polygon.MAX_SIDES`
* :java:package:`com.example.shapes`
* :java:ref:`Canvas.draw(Shape) <Canvas.draw(Shape)>`
* :java:type:`String`, :java:type:`List`, :java:type:`Pair`
* :java:extdoc:`java.util.Map.Entry`, :java:extdoc:`~org.javatuples.Triplet`
* :any:`Point`
