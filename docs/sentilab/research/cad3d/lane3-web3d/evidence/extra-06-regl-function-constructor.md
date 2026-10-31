# extra-06: regl compiles its draw commands with the Function constructor

- Input: `package/dist/regl.js` from the npm tarball regl-2.1.1.tgz downloaded by the web-stack research (web-08), whose sha512 matched `dist.integrity` (regl 2.1.1 integrity=MATCH sha1=MATCH expected=sha512-+IOGrx).
- SHA-256 of the file: `9c32ed6d3318ceb6cd440464dce0abc93dd05f7a67d1e02e5c38252e2b88518e`; read with grep only, never executed.

```text
 6000      return result
 6001    }
 6002  
 6003    function compile () {
 6004      var code = ['"use strict";',
 6005        globalBlock,
 6006        'return {']
 6007      Object.keys(procedures).forEach(function (name) {
 6008        code.push('"', name, '":', procedures[name].toString(), ',')
 6009      })
 6010      code.push('}')
 6011      var src = join(code)
 6012        .replace(/;/g, ';\n')
 6013        .replace(/}/g, '}\n')
 6014        .replace(/{/g, '{\n')
 6015      var proc = Function.apply(null, linkedNames.concat(src))
 6016      return proc.apply(null, linkedValues)
 6017    }
```

Reading: `Function.apply(null, names.concat(src))` builds a function from generated source text, which is the Function constructor. Under our CSP (script-src 'self', no 'unsafe-eval'; csp.js:7) that call is refused, so regl's draw commands could not be compiled on our pages.
