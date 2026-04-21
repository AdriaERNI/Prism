Class Test.MCPUtils
{

ClassMethod Greet(name As %String) As %String
{
  Return "Hi, " _ name _ "!"
}

ClassMethod Timestamp() As %String
{
  Return $ZDateTime($Horolog, 3)
}

}