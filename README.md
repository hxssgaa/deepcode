# deepcode
A deep code analyzer focus on module dependency generation and auto unit testing.
Right now, we are only supporting java auto code analyzer.

## There are currently 3 functions:

### 1. Abstract the methods, classes and fields of the static Java class file.
We store the methods, classes and fields of the Java class into python variables, so you can see how many functions and fields of each class.

### 2. Track the dependency tree of Java classes or interfaces.
We can get the dependency tree stored in JSON format of the Java classes based on The fields dependency.

### 3. Auto Java Unit testing of Java classes or interfaces.
Automatically write Java classes unit testing based on the params types of each Java class methods. 
Now we are only supporting random parameter testing, we are going to analyze which range of varible values would affect the 
state of the method, and using more specific parameters to auto unit test the Java classes or interfaces.

### Usage:
(1) tracer.py

For Java dependency generation:

tracer.py [analyze classes directory] [project directory]

(2) ut_gen.py

For Java automatically writing unit testing:

ut_gen.py [classes directory which needs unit testing] [project directory] [target directory]
