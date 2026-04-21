Class Test.MCPPerson Extends %Persistent
{

Property Name As %String(MAXLEN = 100);

Property Age As %Integer(MINVAL = 0, MAXVAL = 200);

Property Email As %String(MAXLEN = 200);

Index NameIndex On Name;

ClassMethod Hello() As %String [ SqlProc ]
{
  Return "Hello from MCP"
}

ClassMethod Add(a As %Integer, b As %Integer) As %Integer [ SqlProc ]
{
  Return a + b
}

}