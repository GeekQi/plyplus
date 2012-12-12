from __future__ import absolute_import

from weakref import ref
from copy import deepcopy
from .stree_collection import STreeCollection

from .utils import StringTypes, StringType, classify, _cache_0args


class Str(StringType):
    # XXX Required to exclude 'parent'
    def __getstate__(self):
        return StringType(self)
    def __setstate__(self, x):
        pass

class STree(object):
    # __slots__ = 'head', 'tail', '_cache', 'parent', 'index_in_parent'

    def __init__(self, head, tail, skip_adjustments=False):
        if skip_adjustments:
            self._head, self._tail = head, tail
            self.clear_cache()
        else:
            self.reset(head, tail)

    def _get_head(self):
        return self._head
    def _set_head(self, head):
        self._head = head
        self.clear_cache()
    head = property(_get_head, _set_head)

    def _get_tail(self):
        return self._tail
    def _set_tail(self, tail):
        self._tail = tail
        if type(tail) != list:
            tail = list(tail)
        for i, x in enumerate(tail):
            if type(x) in StringTypes:
                tail[i] = Str(x)
        self.clear_cache()
    tail = property(_get_tail, _set_tail)

    def reset(self, head, tail):
        "Warning: calculations done on tree will have to be manually re-run on the tail elements"    # XXX
        self._head = head
        self.tail = tail    # clears the cache

    def reset_from_tree(self, tree):
        # self.reset(tree._head, tree._tail)
        self._head = tree._head
        self._tail = tree._tail
        self._cache = tree._cache
        if hasattr(self, 'parent') and self.parent:
            self.parent().clear_cache()

    def clear_cache(self):
        self._cache = {}
        if hasattr(self, 'parent') and self.parent:
            self.parent().clear_cache()

    def expand_kids_by_index(self, *indices):
        for i in sorted(indices, reverse=True): # reverse so that changing tail won't affect indices
            kid = self._tail[i]
            self._tail[i:i+1] = kid._tail
        self.clear_cache()

    def remove_kids_by_index(self, *indices):
        for i in sorted(indices, reverse=True): # reverse so that changing tail won't affect indices
            del self._tail[i]
        self.clear_cache()

    def remove_kid_by_head(self, head):
        for i, child in enumerate(self._tail):
            if child._head == head:
                del self._tail[i]
                self.clear_cache()
                return
        raise ValueError("head not found: %s"%head)

    def remove_kid_by_id(self, child_id):
        for i, child in enumerate(self._tail):
            if id(child) == child_id:
                del self._tail[i]
                self.clear_cache()
                return
        raise ValueError("id not found: %s"%child_id)

    def remove_from_parent(self):
        self.parent().remove_kid_by_id(id(self))
        self.parent = None

    def expand_into_parent(self):
        self.parent().expand_kids_by_index(self.index_in_parent)
        self.parent = None

    def __len__(self):
        raise Exception('len')
    def __nonzero__(self):
        return True    # XXX ???
    def __bool__(self):
        return True    # XXX ???

    @_cache_0args
    def __hash__(self):
        return hash((self._head, tuple(self._tail)))
    def __eq__(self, other):
        try:
            return self._head == other._head and self._tail == other._tail
        except AttributeError:
            return False
    def __ne__(self, other):
        return not (self == other)

    def __getstate__(self):
        return self.head, self.tail
    def __setstate__(self, data):
        self.head, self.tail = data
        self.clear_cache()

    def __deepcopy__(self, memo):
        return type(self)(self.head, deepcopy(self.tail, memo))

    @property
    @_cache_0args
    def named_tail(self):
        "Warning: Assumes 'tail' doesn't change"
        return classify(self._tail, lambda e: is_stree(e) and e._head)

    def leaf(self, leaf_head, default=KeyError):
        try:
            [r] = self.named_tail[leaf_head]
        except KeyError:
            if default == KeyError:
                raise
            r = default
        return r

    def leaves(self, leaf_head):
        return self.leaves_by_pred(lambda x: x.head == leaf_head)

    def leaves_by_pred(self, pred):
        return STreeCollection(filter(pred, self.tail))

    def calc_parents(self):
        for i, kid in enumerate(self.tail):
            if is_stree(kid):
                kid.calc_parents()
            kid.parent = ref(self)
            kid.index_in_parent = i

        if not hasattr(self, 'parent'):
            self.parent = None
            self.index_in_parent = None

    def calc_depth(self, depth=0):
        self.depth = depth
        for kid in self.tail:
            try:
                kid.calc_depth(depth + 1)
            except AttributeError:
                pass

    # == Functional operations (STree -> list) ==

    def find_predicate(self, predicate):
        "XXX Deprecated"
        return self.filter(predicate)

    def map(self, func, context=None):
        if context is None:
            context = [ func(self) ]
        for kid in self._tail:
            if hasattr(kid, 'map'):
                kid.map(func, context)
            context.append( func(kid) )
        return context

    def filter(self, func, context=None):
        if context is None:
            context = []
        if func(self):
            context.append( self )
        for kid in self.tail:
            if hasattr(kid, 'filter'):
                kid.filter(func, context)
        return context

    def reduce(self, func, initial=None):
        return reduce(func, [kid.reduce(func, initial)
                for kid in self.tail
                if hasattr(kid, 'reduce')
            ], initial)

    def count(self):
        return self.reduce(lambda x,y: x+y, 1)

    # == Tree Navigation (assumes parent) ==

    @property
    def is_first_kid(self):
        return self.index_in_parent == 0

    @property
    def is_last_kid(self):
        return self.index_in_parent == len(self.parent().tail)-1

    @property
    def next_kid(self):
        return self.parent().tail[self.index_in_parent + 1]

    @property
    def prev_kid(self):
        new_index = self.index_in_parent - 1
        if new_index < 0:
            # We dont want it to overflow back to the last element
            raise IndexError('First element in tail')
        return self.parent().tail[new_index]

    @property
    def ancestors(self):
        parent = self.parent()
        while parent:
            yield parent
            parent = parent.parent() if parent.parent else None

    # == Output Functions ==

    def _to_pydot(self, graph):
        import pydot
        color = hash(self._head) & 0xffffff
        if not (color & 0x808080):
            color |= 0x808080

        def new_leaf(leaf):
            node = pydot.Node(id(leaf), label=repr(leaf))
            graph.add_node(node)
            return node

        subnodes = [kid._to_pydot(graph) if is_stree(kid) else new_leaf(kid) for kid in self._tail]
        node = pydot.Node(id(self), style="filled", fillcolor="#%x"%color, label=self._head)
        graph.add_node(node)

        for subnode in subnodes:
            graph.add_edge(pydot.Edge(node, subnode))

        return node

    def _pretty(self, indent_str='  '):
        if len(self._tail) == 1 and not is_stree(self._tail[0]):
            return [ indent_str*self.depth, self._head, '\t', self._tail[0], '\n']

        l = [ indent_str*self.depth, self._head, '\n' ]
        for n in self._tail:
            try:
                l += n._pretty(indent_str)
            except AttributeError:
                l += [ indent_str*(self.depth+1), StringType(n), '\n' ]

        return l

    def pretty(self, **kw):
        self.calc_depth()
        return ''.join(self._pretty(**kw))

    def to_png_with_pydot(self, filename):
        import pydot
        graph = pydot.Dot(graph_type='digraph', rankdir="LR")
        self._to_pydot(graph)
        graph.write_png(filename)

    def __repr__(self):
        return '%s(%s)' % (self.head, ', '.join(map(repr,self.tail)))



def is_stree(obj):
    return type(obj) is STree or isinstance(obj, STree)

class SVisitor(object):
    def visit(self, tree):
        assert tree

        open_queue = [tree]
        queue = []

        while open_queue:
            node = open_queue.pop()
            queue.append(node)
            open_queue += filter(is_stree, node.tail)

        for node in reversed(queue):
            getattr(self, node.head, self.__default__)(node)

    def __default__(self, tree):
        pass

class SVisitor_Recurse(object):

    def visit(self, tree):
        self._visit(tree)
        return tree

    def _visit(self, tree):
        pre_f = getattr(self, 'pre_' + tree._head, None)
        if pre_f:
            pre_f(tree)

        for branch in tree._tail:
            if is_stree(branch):
                self._visit(branch)

        f = getattr(self, tree._head, self.__default__)
        return f(tree)

    def __default__(self, tree):
        pass

class STransformer(object):
    def transform(self, tree):
        return self._transform(tree)

    def _transform(self, tree):
        pre_f = getattr(self, 'pre_' + tree.head, None)
        if pre_f:
            return pre_f(tree)

        branches = [
                self._transform(branch) if is_stree(branch) else branch
                for branch in tree._tail
            ]

        new_tree = tree.__class__(tree._head, branches)
        if hasattr(tree, 'depth'):
            new_tree.depth = tree.depth # XXX ugly hack, need a general solution for meta-data (meta attribute?)
        if hasattr(tree, 'parent'):
            # XXX ugly hack, need a general solution for meta-data (meta attribute?)
            new_tree.parent = tree.parent
            new_tree.index_in_parent = tree.index_in_parent

        f = getattr(self, new_tree._head, self.__default__)
        return f(new_tree)

    def __default__(self, tree):
        return tree
