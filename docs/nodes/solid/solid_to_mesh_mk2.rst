Solid to Mesh
=============

Functionality
-------------

Transform Solid data to Mesh Data.

Shape Type
----------

The node can transform a Solid to a Mesh or a Solid Face to mesh

Methods
-------

**Basic**: This method is the fastest offers a Precision option that expects values(and only will be affected)  like 1, 0.1, 0.001. Note that a lower number means more precision. Also when reducing the precision (by giving a greater number) the node may not change until you change the input solid data.

**Standard**: Has the following options

- Surface deviation: Maximal linear deflection of a mesh section from the surface of the object.

- Angular deviation: Maximal angular deflection from one mesh section to the next section.

- Relative surface deviation: If checked, the maximal linear deviation of a mesh segment will be the specified Surface deviation multiplied by the length of the current mesh segment (edge).


**Mefisto**: The only setting is:

- Maximum edge length: If this number is smaller the mesh becomes finer. The smallest value is 0.

**Trivial**: ...

**Lenient**: This mode is based on Yorik van Havre's Blender FCStd importer code, but modified for speed. This mode produces tris, quads and ngons. It may not have coherent polygon normals. This handles curves and polygons with holes. This mode attemps to remove any duplicate/reverse faces. 

If you really want to understand these algorithms, you should read the source code - it is the best reference.


Examples
--------

.. image:: https://raw.githubusercontent.com/vicdoval/sverchok/docs_images/images_for_docs/solid/solid_to_mesh/solid_to_mesh_blender_sverchok_example.png

.. image:: https://raw.githubusercontent.com/vicdoval/sverchok/docs_images/images_for_docs/solid/solid_to_mesh/solid_to_mesh_blender_sverchok_example_01.png
