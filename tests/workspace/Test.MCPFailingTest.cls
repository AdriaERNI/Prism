Class Test.MCPFailingTest Extends %UnitTest.TestCase
{

Method TestWillPass()
{
  Do $$$AssertEquals(1, 1, "This passes")
}

Method TestWillFail()
{
  Do $$$AssertEquals(1, 2, "This should fail: 1 != 2")
}

}