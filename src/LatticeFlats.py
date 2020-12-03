#
#   Copyright 2020 Joshua Maglione 
#
#   Distributed under MIT License
#

from functools import reduce as _reduce
from sage.misc.cachefunc import cached_method

def _parse_poset(P):
    global POS, atoms, labs, int_at
    from os import cpu_count
    from sage.all import Set
    import sage.parallel.decorate as para
    
    POS = P
    N = cpu_count()
    atoms = POS.upper_covers(POS.bottom())

    @para.parallel(N)
    def atom_set(k, shift): 
        S = list(POS._elements[1+shift::k])
        m = lambda x: [x, Set(list(filter(lambda a: POS.le(a, x), atoms)))]
        return list(map(m, S))

    labs = list(atom_set([(N, k) for k in range(N)]))
    labs = [[P.bottom(), Set([])]] + _reduce(lambda x, y: x + y[1], labs, [])
    label_dict = {T[0] : T[1] for T in labs}

    return label_dict

# Can return the subarrangement A_x or restriction A^x simply based on the
# function F given. For subarrangement use 'lambda z: P.lower_covers(z)' and for
# restriction use 'lambda z: P.upper_covers(z)'.
def _subposet(P, x, F):
    from sage.all import Set, Poset
    elts = Set([])
    new_level = Set([x])
    while len(elts.union(new_level)) > len(elts):
        elts = elts.union(new_level)
        new_level = Set(_reduce(
            lambda x, y: x+y, 
            map(F, new_level), 
            []
        ))
    new_P = P.subposet(elts)
    return new_P


# We expand on the function in sage, optimizing a little bit. This makes little
# difference in small ranks but noticeable difference in larger ranks. This is
# still quite slow. 
def _intersection_poset(A):
    from sage.geometry.hyperplane_arrangement.affine_subspace import AffineSubspace
    from sage.all import exists, flatten, Set, QQ, VectorSpace, Poset
    K = A.base_ring()
    whole_space = AffineSubspace(0, VectorSpace(K, A.dimension()))
    # L is the ranked list of affine subspaces in L(A).
    L = [[whole_space], list(map(lambda H: H._affine_subspace(), A))]
    # hyp_cont is the ranked list describing which hyperplanes contain the
    # corresponding intersection. 
    hyp_cont = [[Set([])], [Set([k]) for k in range(len(A))]]
    active = True
    codim = 1
    while active:
        active = False
        new_level = []
        # new_label = []
        new_hypcont = []
        for i in range(len(L[codim])):
            T = L[codim][i]
            for j in range(len(A)):
                # Skip the hyperplane already known to contain the intersection.
                if not j in hyp_cont[codim][i]: 
                    H = A[j]
                    I = H._affine_subspace().intersection(T)
                    # Check if the intersection is trivial.
                    if I is not None:
                        if I == T: 
                            # This case means that H cap T = T, so we should
                            # record that H contains T.
                            hyp_cont[codim][i] = hyp_cont[codim][i].union(
                                Set([j])
                            )
                        else:
                            # Check if we have this intersection already. 
                            is_in, ind = exists(
                                range(len(new_level)), 
                                lambda k: I == new_level[k]
                            )
                            if is_in:
                                # We have the intersection, so we update
                                # containment info accordingly. 
                                new_hypcont[ind] = new_hypcont[ind].union(
                                    Set([j]).union(hyp_cont[codim][i])
                                )
                            else:
                                # We do not have it, so we update everything.
                                new_level.append(I)
                                new_hypcont.append(
                                    hyp_cont[codim][i].union(Set([j]))
                                )
                                active = True
        if active:
            L.append(new_level)
            hyp_cont.append(new_hypcont)
        codim += 1
    
    L = flatten(hyp_cont)
    t = {}
    for i in range(len(L)):
        t[i] = Set(list(map(lambda x: x+1, L[i])))
    cmp_fn = lambda p, q: t[p].issubset(t[q])
    label_dict = {i : t[i] for i in range(len(L))}
    hyp_dict = {i + 1 : A[i] for i in range(len(A))}
    
    return [Poset((t, cmp_fn)), label_dict, hyp_dict]


class LatticeOfFlats():

    def __init__(self, A=None, poset=None, flat_labels=None, 
    hyperplane_labels=None, lazy=False, nature_hyperplane_label=True):
        self.hyperplane_arrangement = A
        self.poset = poset 
        self.flat_labels = flat_labels
        self.hyperplane_labels = hyperplane_labels
        if poset != None:
            assert poset.has_bottom(), "Expected a unique minimal element in poset."
            assert poset.is_graded(), "Expected a graded poset."
            self.poset = poset
            self.flat_labels = None
        else:
            if not lazy:
                P, FL, HL = _intersection_poset(A)
                self.poset = P
                self.flat_labels = FL
                self.hyperplane_labels = HL
        if self.flat_labels == None and not lazy:
            self.flat_labels = _parse_poset(poset)
            if hyperplane_labels == None and nature_hyperplane_label:
                self.hyperplane_labels = {i - 1 : A[i] for i in range(len(A))}


    def __repr__(self):
        if self.hyperplane_arrangement:
            return "The lattice of flats of:\n{0}\ngiven by:\n{1}".format(self.hyperplane_arrangement, self.poset)
        else:
            return "The lattice of flats of some matroid given by:\n{0}".format(self.poset)

    def atoms(self):
        return self.poset.upper_covers(self.poset.bottom())

    def labels_of_flats(self):
        elt_tup = lambda x: tuple([x, self.flat_labels[x]])
        return list(map(elt_tup, self.poset._elements))

    def labels_of_hyperplanes(self):
        P = self.poset 
        elt_tup = lambda x: tuple([x, self.hyperplane_labels[x]])
        return list(map(elt_tup, P.upper_covers(P.bottom())))

    def proper_part_poset(self):
        P = self.poset
        return P.subposet(P._elements.remove(P.top()).remove(P.bottom()))

    def show(self):
        self.poset.show()

    def subarrangement(self, x):
        P = self.poset 
        if type(x) != set:
            assert x in P, "Expected element to be in poset."
            new_P = _subposet(P, x, lambda z: P.lower_covers(z))
            new_A = None 
            new_FL = None
            new_HL = None 
            if self.hyperplane_arrangement and self.hyperplane_labels:
                A = self.hyperplane_arrangement
                HL = self.hyperplane_labels
                atoms = new_P.upper_covers(new_P.bottom())
                keep = list(map(lambda k: HL[k], atoms))
                new_A = A.parent()(keep)
                new_HL = {a : HL[a] for a in atoms}
            if self.flat_labels:
                FL = self.flat_labels
                new_FL = {x : FL[x] for x in new_P._elements}
            return LatticeOfFlats(new_A, poset=new_P, flat_labels=new_FL, hyperplane_labels=new_HL)
        else:
            L = self.flat_labels 
            X = list(filter(lambda y: L[y] == x, P._elements))
            try:
                return self.subarrangement(X[0])
            except IndexError:
                raise ValueError("No element labeled by:\n{0}".format(x))
    
    def restriction(self, x):
        P = self.poset 
        if type(x) != set:
            assert x in P, "Expected element to be in poset."
            new_P = _subposet(P, x, lambda z: P.upper_covers(z))
            A = None 
            if self.hyperplane_arrangement and self.hyperplane_labels:
                A = self.hyperplane_arrangement
                HL = self.hyperplane_labels
                if P.covers(P.bottom(), x):
                    A = A.restriction(HL[x])
                # How can we relabel hyperplanes? 
            return LatticeOfFlats(A, poset=new_P)
        else:
            L = self.flat_labels 
            X = list(filter(lambda y: L[y] == x, P._elements))
            try:
                return self.restriction(X[0])
            except IndexError:
                raise ValueError("No element labeled by:\n{0}".format(x))
    
    def deletion(self, H):
        from sage.all import Set

        P = self.poset
        L = self.flat_labels

        if type(H) == set:
            L = self.flat_labels 
            X = list(filter(lambda y: L[y] == H, P._elements))
            try:
                return self.deletion(X[0])
            except IndexError:
                raise ValueError("No element labeled by:\n{0}".format(H))
            
        assert P.rank_function()(H) == 1, "Expected an atom."

        if P.has_top():
            coatoms = P.lower_covers(P.top())
        else:
            # not really coatoms... but whatever
            coatoms = P.maximal_elements()

        m = len(P.upper_covers(P.bottom())) - 1
        def check(C):
            S = L[C]
            return bool(len(S) == m and not H in S)
        new_top = list(filter(check, coatoms))

        if len(new_top) == 1:
            new_P = _subposet(P, new_top[0], lambda z: P.lower_covers(z))
            new_labels = {y : L[y] for y in new_P._elements}
        else:
            def good_flats(F):
                S = L[F]
                if H in S:
                    U = S.difference(Set([H]))
                    return (U != 0) and (not U in L.values())
                else:
                    return True
            flats = list(filter(good_flats, P._elements))
            new_P = P.subposet(flats)
            new_labels = {y : L[y].difference(Set([H])) for y in flats}

        if self.hyperplane_arrangement:
            HPA = self.hyperplane_arrangement
            HPA = HPA.parent()(HPA[:H-1] + HPA[H:])
        else:
            HPA = None

        return LatticeOfFlats(HPA, poset=new_P, labels=new_labels)

    def lazy_restriction(self, H):
        HPA = self.hyperplane_arrangement
        assert HPA != None, "Needs underlying hyperplane arrangement."
        A = HPA.restriction(HPA[H - 1])
        return LatticeOfFlats(A, lazy=True)

    def lazy_deletion(self, H):
        HPA = self.hyperplane_arrangement
        assert HPA != None, "Needs underlying hyperplane arrangement."
        return LatticeOfFlats(HPA.parent()(HPA[:H-1] + HPA[H:]), lazy=True)

    @cached_method
    def Poincare_polynomial(self):
        from sage.all import QQ
        from sage.rings.polynomial.polynomial_ring import polygen
        X = polygen(QQ, 'X')
        if self.poset != None:
            P = self.poset 
            atoms = self.atoms()
            if P.rank() == 0:
                return QQ(1)
            if P.rank() == 1:
                return QQ(1) + len(atoms)*X
            H = atoms[0]
        else: 
            # Lazy 
            A = self.hyperplane_arrangement
            assert A != None, "Expected either a poset or hyperplane arrangement."
            if A.rank() == 0:
                return QQ(1)
            if A.rank() == 1:
                return QQ(1) + len(A)*X
            H = 1
        D = self.lazy_deletion(H)
        R = self.lazy_restriction(H)
        return D.Poincare_polynomial() + X*R.Poincare_polynomial()
        
    @cached_method
    def _combinatorial_eq_elts(self):
        global POS, P_elts
        from os import cpu_count
        import sage.parallel.decorate as para

        N = cpu_count()
        POS = self.poset
        P_elts = POS._elements.remove(POS.top()).remove(POS.bottom())

        @para.parallel(N)
        def match_elts(k, shift):
            all_elts = P_elts[shift::k]
            eq_elts = []
            counts = []
            down = []
            restrict = []
            while len(all_elts) > 0:
                x = all_elts[0]
                dow_x = _subposet(POS, x, lambda z: POS.lower_covers(z))
                res_x = _subposet(POS, x, lambda z: POS.upper_covers(z))
                match = False
                i = 0
                while not match and i < len(eq_elts):
                    if dow_x.is_isomorphic(down[i]) and res_x.is_isomorphic(restrict[i]):
                        match = True
                    else:
                        i += 1
                if match:
                    counts[i] += 1
                else:
                    eq_elts.append(x)
                    counts.append(1)
                    down.append(dow_x)
                    restrict.append(res_x)
                all_elts = all_elts[1:]
            return list(zip(eq_elts, counts, down, restrict))

        # Get the preliminary set of inequivalent elements
        prelim_elts = list(match_elts([(N, k) for k in range(N)]))
        prelim_elts = _reduce(lambda x, y: x + y[1], prelim_elts, [])

        # Test further to minimize the size. 
        equiv_elts = []
        while len(prelim_elts) > 0:
            x = prelim_elts[0]
            match = False
            i = 0
            while not match and i < len(equiv_elts):
                if x[2].is_isomorphic(equiv_elts[i][2]) and x[3].is_isomorphic(equiv_elts[i][3]):
                    match = True
                else:
                    i += 1
            if match:
                equiv_elts[i][1] += x[1]
            else:
                equiv_elts.append(list(x))
            prelim_elts = prelim_elts[1:]
        return equiv_elts


# The deletion method is coded well enough to allow for this kind of recursion. 
# We need the new labels for a hyperplane though.
def _deletion(A, X, P, poset=True, OG=None):
    if OG:
        Ar = OG
    else:
        Ar = A
    H_to_str = lambda H: str(list(Ar).index(H))
    complement = filter(lambda H: not P.le(H_to_str(H), X), A)
    B = _reduce(lambda x, y: x.deletion(y), complement, A)
    if not poset:
        return B
    Q = _subposet(P, X, lambda z: P.lower_covers(z))
    return B, Q


def _Coxeter_poset_data():
    # Bell numbers: A000110
    def A_poset(n):
        from sage.all import binomial
        S = [1, 1, 2, 5, 15, 52, 203]
        while len(S) <= n+1:
            m = len(S) - 1
            S.append(_reduce(
                lambda x, y: x + y[0]*binomial(m, y[1]), zip(S, range(m+1)), 0
            ))
        return S[n+1]
    def S(n, k, m):
        if k > n or k < 0 : 
            return 0
        if n == 0 and k == 0: 
            return 1
        return S(n-1, k-1, m) + (m*(k+1)-1)*S(n-1, k, m)
    def A007405(n): 
        from sage.all import add
        return add(S(n, k, 2) for k in (0..n)) # Peter Luschny, May 20 2013
    # D analog of Bell numbers: A039764
    Dlist = [1, 1, 4, 15, 72, 403, 2546, 17867, 137528, 1149079, 10335766, 99425087, 1017259964, 11018905667, 125860969266, 1510764243699, 18999827156304, 249687992188015, 3420706820299374, 48751337014396167]
    table = {
        'A': {
            'hyperplanes': lambda n: n*(n+1) // 2,
            'poset': A_poset
        },
        'B': {
            'hyperplanes': lambda n: n**2,
            'poset': A007405
        },
        'D': {
            'hyperplanes': lambda n: n**2 - n,
            'poset': lambda n: Dlist[n]
        }
    }
    return table

def _possibly_Coxeter(P):
    r = P.rank()
    hypers = list(filter(lambda x: P.covers(P.bottom(), x), P))
    m = len(hypers)
    CPD = _Coxeter_poset_data()
    for name in ['A', 'B', 'D']:
        if CPD[name]['hyperplanes'](r) == m:
            if CPD[name]['poset'](r) == len(P):
                return [True, name]
    return [False, None]



# Compute the Poincare polynomial of either the chain F or the upper ideal of P
# at restrict. 
def PoincarePolynomial(P, F=None, restrict=None):
    from .Globals import __DEFAULT_p as p
    from sage.all import var, ZZ

    # Setup the data
    if restrict != None:
        F = [restrict]
    if F == None:
        assert P.has_bottom()
        F = [P.bottom()]
    if F[0] != P.bottom():
        F = [P.bottom()] + F 

    P_up = _subposet(P, F[-1], lambda z: P.upper_covers(z))
    chi = P_up.characteristic_polynomial() 
    d = chi.degree()
    p = var(p)
    pi = ((-p)**d*chi(q=-p**(-1))).expand().simplify()
    if F[-1] == P.bottom() or restrict != None:
        return pi
    P_down = _subposet(P, F[-1], lambda z: P.lower_covers(z))
    return pi*PoincarePolynomial(P_down, F=F[:-1])
