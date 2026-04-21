Class Test.MCPBgHelper Extends %RegisteredObject
{

ClassMethod DelayAndReturn(text As %String, seconds As %Integer = 2) As %String
{
  Hang seconds
  Return text
}

}
