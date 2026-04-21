Class Test.MCPSampleTest Extends %UnitTest.TestCase
{

Method TestAddition()
{
  Do $$$AssertEquals(2 + 3, 5, "2 + 3 should equal 5")
}

Method TestStringConcat()
{
  Set result = "Hello" _ " " _ "World"
  Do $$$AssertEquals(result, "Hello World", "String concat works")
}

Method TestTruth()
{
  Do $$$AssertTrue(1, "1 is truthy")
}

}