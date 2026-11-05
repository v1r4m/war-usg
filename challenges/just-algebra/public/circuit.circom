pragma circom 2.1.0;

template H2() {
    signal input a;
    signal input b;
    signal output y;

    signal t <== a + 3 * b + 42;
    signal sq <== t * t;
    y <== sq + 1337;
}

template Switch2() {
    signal input x[2];
    signal input k;
    signal output y[2];

    // k must be a bit
    signal k2 <== k * k;
    signal k3 <== k2 * k;
    k3 * k === k;

    signal d <== x[1] - x[0];
    y[0] <== x[0] + (2 * k - k2) * d;
    y[1] <== x[1] - k * d;
}

template Verifier(n) {
    signal input leaf;
    signal input root;
    signal input elems[n];
    signal input sel[n];

    component hs[n];
    component sw[n];

    signal cur[n + 1];
    cur[0] <== leaf;

    for (var i = 0; i < n; i++) {
        sw[i] = Switch2();
        sw[i].x[0] <== cur[i];
        sw[i].x[1] <== elems[i];
        sw[i].k <== sel[i];

        hs[i] = H2();
        hs[i].a <== sw[i].y[0];
        hs[i].b <== sw[i].y[1];

        cur[i + 1] <== hs[i].y;
    }

    root === cur[n];
}

component main {public [root, leaf, elems]} = Verifier(10);
