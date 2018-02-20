// Inserting fun comment here
var test = require('unit.js');
var str = 'Hello, world!';

var a = [];
if (!a.length) {
  console.log('winning');
}

function FakeFunction() {
}

test.string(str).startsWith('Hello');

if (test.string(str).startsWith('Hello')) {
  console.log('Passed');
}
