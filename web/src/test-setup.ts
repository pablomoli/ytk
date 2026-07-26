import "@testing-library/jest-dom";

/* Tests run in real Chromium (#135), which supplies matchMedia and
   localStorage itself. The stubs that used to live here existed only because
   jsdom lacked one and Node's inert global shadowed the other. Suites that
   touch stored preferences clear localStorage in their own beforeEach. */
